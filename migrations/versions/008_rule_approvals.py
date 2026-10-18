"""Per-person decisions on protected rule-text proposals (task 2c56ad7a)."""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rule_approvals',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('proposal', sa.Text, nullable=False),
        sa.Column('sha256', sa.Text, nullable=False),
        sa.Column('decided_by', sa.Text, nullable=False),
        sa.Column('principal_id', sa.Text, nullable=False),
        sa.Column('decision', sa.Text, nullable=False),
        sa.Column('note', sa.Text, nullable=False),
        sa.Column('decided_at', sa.Text, nullable=False),
        sa.CheckConstraint("decision IN ('yes','no','change')", name='ck_rule_approval_decision'),
        sa.CheckConstraint('length(sha256) = 64', name='ck_rule_approval_sha'),
        sa.UniqueConstraint('sha256', 'decided_by', name='uq_rule_approval_person'))


def downgrade():
    op.drop_table('rule_approvals')
