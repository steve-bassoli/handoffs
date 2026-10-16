"""Persist AI attempts and task lineage without changing the wallet."""
from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE bounties ADD COLUMN parent_id TEXT REFERENCES bounties(id)')
    op.execute('''CREATE TABLE ai_runs (
        id TEXT PRIMARY KEY, bounty_id TEXT NOT NULL UNIQUE REFERENCES bounties(id),
        actor TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL,
        data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )''')


def downgrade():
    raise NotImplementedError('Keep a database backup before migration.')
