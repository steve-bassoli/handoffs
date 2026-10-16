"""Initial prototype schema."""
from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

TABLES = [
    """CREATE TABLE users (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, alias TEXT NOT NULL
    )""",
    """CREATE TABLE bounties (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL,
        criteria TEXT NOT NULL, repository TEXT NOT NULL, context_links TEXT NOT NULL,
        creator TEXT NOT NULL REFERENCES users(id), target TEXT REFERENCES users(id),
        gold INTEGER NOT NULL CHECK(gold > 0), created_at TEXT NOT NULL,
        legacy TEXT, funded INTEGER NOT NULL DEFAULT 1 CHECK(funded IN (0,1))
    )""",
    """CREATE TABLE events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, bounty_id TEXT NOT NULL REFERENCES bounties(id),
        kind TEXT NOT NULL, actor TEXT NOT NULL REFERENCES users(id),
        state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE deliveries (
        id TEXT PRIMARY KEY, bounty_id TEXT NOT NULL REFERENCES bounties(id),
        actor TEXT NOT NULL REFERENCES users(id), pr_url TEXT NOT NULL,
        evidence TEXT NOT NULL, simulated INTEGER NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE accounts (
        id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), kind TEXT NOT NULL
    )""",
    """CREATE TABLE gold_transactions (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, bounty_id TEXT REFERENCES bounties(id),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE gold_entries (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL REFERENCES gold_transactions(id),
        account_id TEXT NOT NULL REFERENCES accounts(id), amount INTEGER NOT NULL
    )""",
    """CREATE TABLE monthly_allocations (
        user_id TEXT NOT NULL REFERENCES users(id), month TEXT NOT NULL,
        gold INTEGER NOT NULL CHECK(gold > 0), PRIMARY KEY(user_id, month)
    )""",
    """CREATE TABLE operations (
        actor TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL,
        fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(actor, key)
    )""",
    """CREATE TABLE import_records (
        source TEXT NOT NULL, source_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
        data TEXT NOT NULL, PRIMARY KEY(source, source_id)
    )""",
]


def upgrade():
    for sql in TABLES:
        op.execute(sql)


def downgrade():
    raise NotImplementedError('Keep a database backup before migration.')
