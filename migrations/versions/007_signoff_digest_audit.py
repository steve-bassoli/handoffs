"""Sign-off change requests and digest decision audit (decision digest LOW-5)."""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('signoffs', sa.Column('change_note', sa.Text))
    op.add_column('signoffs', sa.Column('change_requested_by', sa.Text))
    op.add_column('signoffs', sa.Column('change_requested_at', sa.Integer))
    op.add_column('signoffs', sa.Column('digest_audit_json', sa.Text))


def downgrade():
    with op.batch_alter_table('signoffs') as batch:
        for column in ('digest_audit_json', 'change_requested_at', 'change_requested_by', 'change_note'):
            batch.drop_column(column)
