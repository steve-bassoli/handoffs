"""Human decisions bound to exact protected-action payloads."""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('signoffs',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('action', sa.Text, nullable=False),
        sa.Column('payload_sha256', sa.Text, nullable=False),
        sa.Column('payload_json', sa.Text, nullable=False),
        sa.Column('summary', sa.Text, nullable=False),
        sa.Column('requested_by', sa.Text, nullable=False),
        sa.Column('requested_principal', sa.Text, nullable=False),
        sa.Column('requested_principal_id', sa.Text, nullable=False),
        sa.Column('created_at', sa.Integer, nullable=False),
        sa.Column('decided_by', sa.Text),
        sa.Column('decided_principal', sa.Text),
        sa.Column('decided_principal_id', sa.Text),
        sa.Column('decision', sa.Text),
        sa.Column('decision_note', sa.Text),
        sa.Column('decision_mode', sa.Text),
        sa.Column('decided_at', sa.Integer),
        sa.Column('used_at', sa.Integer),
        sa.CheckConstraint("action IN ('automation_mode','spend_ceiling','price_checkpoint','rule_texts','publish')", name='ck_signoff_action'),
        sa.CheckConstraint("decision IS NULL OR decision IN ('approved','rejected')", name='ck_signoff_decision'),
        sa.CheckConstraint("(decision IS NULL AND decided_by IS NULL AND decided_principal IS NULL AND decision_mode IS NULL AND decided_principal_id IS NULL AND decided_at IS NULL AND decision_note IS NULL) OR (decision IS NOT NULL AND decided_by IS NOT NULL AND decided_principal IS NOT NULL AND decision_mode IN ('human','prototype-auto') AND decided_principal_id IS NOT NULL AND decided_at IS NOT NULL AND decision_note IS NOT NULL)", name='ck_signoff_human_decision'),
        sa.CheckConstraint("used_at IS NULL OR (decision IS NOT NULL AND decision = 'approved')", name='ck_signoff_used'))
    op.create_index('ix_signoffs_pending', 'signoffs', ['decision', 'created_at'])


def downgrade():
    op.drop_index('ix_signoffs_pending', table_name='signoffs')
    op.drop_table('signoffs')
