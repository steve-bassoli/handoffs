"""Versioned advisory snapshots; not approvals or execution authority."""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('recommendations',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('item_kind', sa.Text, nullable=False),
        sa.Column('item_id', sa.Text, nullable=False),
        sa.Column('item_revision', sa.Text, nullable=False),
        sa.Column('disposition', sa.Text, nullable=False),
        sa.Column('rationale', sa.Text, nullable=False),
        sa.Column('provenance_json', sa.Text, nullable=False),
        sa.Column('requester_context', sa.Text, nullable=False),
        sa.Column('created_by', sa.Text, nullable=False),
        sa.Column('created_principal', sa.Text, nullable=False),
        sa.Column('created_at', sa.Integer, nullable=False),
        sa.Column('superseded_by', sa.Text, sa.ForeignKey('recommendations.id')),
        sa.CheckConstraint("item_kind IN ('signoff','intake_veto','human_close','policy_decision')", name='ck_recommendation_kind'),
        sa.CheckConstraint("disposition IN ('yes','no','change')", name='ck_recommendation_disposition'),
        sa.CheckConstraint('length(item_revision) = 64', name='ck_recommendation_revision'),
        sa.CheckConstraint('superseded_by IS NULL OR superseded_by <> id', name='ck_recommendation_successor'))
    op.create_index('ix_recommendations_history', 'recommendations', ['item_kind', 'item_id', 'created_at'])
    # One effective snapshot per item, including across revisions. This also
    # prevents equal timestamps from making current selection ambiguous.
    op.create_index('uq_recommendations_current', 'recommendations', ['item_kind', 'item_id'], unique=True,
                    sqlite_where=sa.text('superseded_by IS NULL'),
                    postgresql_where=sa.text('superseded_by IS NULL'))


def downgrade():
    op.drop_index('uq_recommendations_current', table_name='recommendations')
    op.drop_index('ix_recommendations_history', table_name='recommendations')
    op.drop_table('recommendations')
