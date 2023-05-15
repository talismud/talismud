"""add_filter_to_location

Revision ID: f3a0a2c0641a
Revises:
Create Date: 2023-05-15 14:17:29.174352

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a0a2c0641a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("node", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("location_filter", sa.String(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("node", schema=None) as batch_op:
        batch_op.drop_column("location_filter")
