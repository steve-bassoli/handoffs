"""Rename work records; retain a reversible journal for changed stored labels.

Requires SQLite >= 3.26. Native RENAME operations preserve rows, constraints,
foreign-key targets and indexes without disabling foreign-key enforcement.
The batch contexts deliberately execute native SQL, not Alembic's copy/drop
alter_column fallback. See the delivery checkpoint for this strategy decision.
"""
import json
import re

from alembic import op

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

JOURNAL = '_task_rename_003'
CHILDREN = ('events', 'deliveries', 'gold_transactions', 'ai_runs')
KINDS = {
    'bounty_paid': 'task_paid',
    'bounty_funded': 'task_funded',
    'bounty_refunded': 'task_refunded',
    'bounty_edited': 'task_edited',
    'bounty_decision': 'task_decision',
    'opportunity_updated': 'task_updated',
}
WORD = re.compile(r'(?<![A-Za-z0-9])(?:opportunities|opportunity|bounties|bounty|opp)(?![A-Za-z0-9])', re.I)


def q(value):
    return '"' + value.replace('"', '""') + '"'


def renamed(value):
    def substitute(match):
        text = match.group()
        replacement = 'tasks' if text.lower() in ('bounties', 'opportunities') else 'task'
        if text.isupper():
            return replacement.upper()
        if text[0].isupper():
            return replacement.capitalize()
        return replacement
    return WORD.sub(substitute, value)


def connection():
    c = op.get_bind()
    if c.dialect.name != 'sqlite':
        raise RuntimeError('Revision 003 supports SQLite only; review other engines separately')
    version = tuple(int(n) for n in c.exec_driver_sql('SELECT sqlite_version()').scalar().split('.')[:3])
    if version < (3, 26, 0):
        raise RuntimeError('Revision 003 requires SQLite >= 3.26 for safe native renames')
    if c.exec_driver_sql('PRAGMA legacy_alter_table').scalar():
        raise RuntimeError('Disable legacy_alter_table before revision 003')
    if list(c.exec_driver_sql('PRAGMA foreign_key_check')):
        raise RuntimeError('Existing foreign-key violations; restore integrity before revision 003')
    return c


def remember(c, table, column, key_column, key, old, new):
    c.exec_driver_sql(
        'INSERT INTO ' + q(JOURNAL) + '(record) VALUES (?)',
        (json.dumps([table, column, key_column, key, old, new]),),
    )


def move_account(c, old_id, new_id):
    """Re-key an account without breaking gold_entries' foreign key: copy, repoint, delete."""
    c.exec_driver_sql('INSERT INTO accounts(id, user_id, kind) SELECT ?, user_id, kind FROM accounts WHERE id=?', (new_id, old_id))
    c.exec_driver_sql('UPDATE gold_entries SET account_id=? WHERE account_id=?', (new_id, old_id))
    c.exec_driver_sql('DELETE FROM accounts WHERE id=?', (old_id,))


def native(table, sql):
    # execute() in a batch context sends this supported SQLite DDL unchanged.
    with op.batch_alter_table(table, recreate='never') as batch:
        batch.execute(sql)


def schema_forward():
    native('bounties', 'ALTER TABLE bounties RENAME TO tasks')
    for table in CHILDREN:
        native(table, 'ALTER TABLE ' + q(table) + ' RENAME COLUMN bounty_id TO task_id')


def schema_backward():
    for table in reversed(CHILDREN):
        native(table, 'ALTER TABLE ' + q(table) + ' RENAME COLUMN task_id TO bounty_id')
    native('tasks', 'ALTER TABLE tasks RENAME TO bounties')


def upgrade():
    c = connection()
    op.create_table(JOURNAL, __import__('sqlalchemy').Column('seq', __import__('sqlalchemy').Integer, primary_key=True),
                    __import__('sqlalchemy').Column('record', __import__('sqlalchemy').Text, nullable=False))
    schema_forward()
    for table, key in (('events', 'seq'), ('gold_transactions', 'id')):
        for identity, old in list(c.exec_driver_sql('SELECT ' + q(key) + ',kind FROM ' + q(table))):
            new = KINDS.get(old, renamed(old))
            if old != new:
                remember(c, table, 'kind', key, identity, old, new)
                c.exec_driver_sql('UPDATE ' + q(table) + ' SET kind=? WHERE ' + q(key) + '=?', (new, identity))

    # Preflight the complete account-name mapping before changing any names.
    accounts = list(c.exec_driver_sql('SELECT id,kind FROM accounts'))
    changes = {identity: renamed(identity) for identity, _ in accounts if renamed(identity) != identity}
    destinations = [changes.get(identity, identity) for identity, _ in accounts]
    if len(destinations) != len(set(destinations)):
        raise RuntimeError('Account rename collision; no accounts may be merged')
    # An opaque work-record ID containing a legacy token needs human handling:
    # blindly changing escrow:<that ID> would break the service lookup contract.
    ids = {row[0] for row in c.exec_driver_sql('SELECT id FROM tasks')}
    if any(old.startswith('escrow:') and old[7:] in ids for old in changes):
        raise RuntimeError('Legacy token in opaque escrow work-record ID; explicit mapping required')
    prior_defer = c.exec_driver_sql('PRAGMA defer_foreign_keys').scalar()
    c.exec_driver_sql('PRAGMA defer_foreign_keys=ON')
    for identity, old_kind in accounts:
        new_id = changes.get(identity, identity)
        if new_id != identity:
            remember(c, 'accounts', 'id', 'id', identity, identity, new_id)
            move_account(c, identity, new_id)
        new_kind = renamed(old_kind)
        if new_kind != old_kind:
            remember(c, 'accounts', 'kind', 'id', new_id, old_kind, new_kind)
            c.exec_driver_sql('UPDATE accounts SET kind=? WHERE id=?', (new_kind, new_id))

    # Historical schemas declare no explicit named indexes, but preserve and
    # rename any deployed non-automatic index names, including partial indexes.
    indexes = list(c.exec_driver_sql("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"))
    names = {name for name, _, _ in indexes}
    targets = [renamed(name) for name, _, _ in indexes]
    if len(targets) != len(set(targets)):
        raise RuntimeError('Index rename collision')
    for name, table, sql in indexes:
        new = renamed(name)
        if new == name:
            continue
        if new in names:
            raise RuntimeError('Index destination already exists: ' + new)
        # SQLite stores CREATE INDEX SQL with its updated table/column names.
        # Replace only the declared index name, not predicates or expressions.
        match = re.match(r'(?is)^(CREATE\s+(?:UNIQUE\s+)?INDEX\s+)(?:"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]|\S+)(\s+ON\s+.*)$', sql)
        if not match:
            raise RuntimeError('Unrecognized CREATE INDEX SQL: ' + name)
        remember(c, '__index__', 'sql', table, name, sql, new)
        c.exec_driver_sql('DROP INDEX ' + q(name))
        c.exec_driver_sql(match.group(1) + q(new) + match.group(2))
    if list(c.exec_driver_sql('PRAGMA foreign_key_check')):
        raise RuntimeError('Foreign-key violations after rename')
    if not prior_defer:
        c.exec_driver_sql('PRAGMA defer_foreign_keys=OFF')


def downgrade():
    c = connection()
    prior_defer = c.exec_driver_sql('PRAGMA defer_foreign_keys').scalar()
    c.exec_driver_sql('PRAGMA defer_foreign_keys=ON')
    records = [json.loads(row[0]) for row in c.exec_driver_sql('SELECT record FROM ' + q(JOURNAL) + ' ORDER BY seq DESC')]
    for table, column, key_column, key, old, new in records:
        if table == '__index__':
            c.exec_driver_sql('DROP INDEX ' + q(new))
            c.exec_driver_sql(old)
            continue
        lookup = new if table == 'accounts' and column == 'id' else key
        current = c.exec_driver_sql('SELECT ' + q(column) + ' FROM ' + q(table) + ' WHERE ' + q(key_column) + '=?', (lookup,)).first()
        if current is None or current[0] != new:
            raise RuntimeError('Journal target changed or disappeared; restore from backup instead')
        if table == 'accounts' and column == 'id':
            move_account(c, new, old)
        else:
            c.exec_driver_sql('UPDATE ' + q(table) + ' SET ' + q(column) + '=? WHERE ' + q(key_column) + '=?', (old, lookup))
    schema_backward()
    if list(c.exec_driver_sql('PRAGMA foreign_key_check')):
        raise RuntimeError('Foreign-key violations after downgrade')
    op.drop_table(JOURNAL)
    if not prior_defer:
        c.exec_driver_sql('PRAGMA defer_foreign_keys=OFF')
