"""Manual step cards in Decisions: steps only a person can do (task 88d917bf)."""
from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('manual_steps',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('what', sa.Text, nullable=False),
        sa.Column('where_text', sa.Text, nullable=False),
        sa.Column('why', sa.Text, nullable=False),
        sa.Column('success', sa.Text, nullable=False),
        sa.Column('state', sa.Text, nullable=False),
        sa.Column('created_by', sa.Text, nullable=False),
        sa.Column('created_utc', sa.Text, nullable=False),
        sa.Column('outcome', sa.Text),
        sa.Column('note', sa.Text),
        sa.Column('decided_by', sa.Text),
        sa.Column('decided_utc', sa.Text),
        sa.Column('revision', sa.Text, nullable=False),
        sa.CheckConstraint("state IN ('open','done','could_not')", name='ck_manual_step_state'),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('done','could_not')", name='ck_manual_step_outcome'))


def downgrade():
    op.drop_table('manual_steps')
