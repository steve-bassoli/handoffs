"""Prototype human passwords and separately attributable principal tokens."""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('human_passwords',
        sa.Column('user_id', sa.Text, sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('salt', sa.Text, nullable=False),
        sa.Column('password_hash', sa.Text, nullable=False),
        sa.Column('iterations', sa.Integer, nullable=False))
    op.create_table('principal_tokens',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('user_id', sa.Text, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('token_hash', sa.Text, nullable=False, unique=True),
        sa.Column('created_at', sa.Integer, nullable=False),
        sa.Column('expires_at', sa.Integer, nullable=False),
        sa.Column('revoked', sa.Integer, nullable=False, server_default='0'),
        sa.CheckConstraint("kind IN ('human','relay','codex','agent')", name='ck_principal_kind'),
        sa.CheckConstraint('revoked IN (0,1)', name='ck_token_revoked'))


def downgrade():
    op.drop_table('principal_tokens')
    op.drop_table('human_passwords')
