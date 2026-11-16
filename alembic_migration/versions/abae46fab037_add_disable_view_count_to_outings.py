"""Add disable view count to outings.

Revision ID: abae46fab037
Revises: 2d710311ac56
Create Date: 2024-01-19 08:05:11.433263

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'abae46fab037'
down_revision = '2d710311ac56'
branch_labels = None
depends_on = None


def upgrade():
    # a versioned attribute of the outings, as `disable_comments`: the
    # counter of the existing outings is enabled, as for the new ones
    for table in ('outings', 'outings_archives'):
        op.add_column(
            table,
            sa.Column(
                'disable_view_count',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
            schema='guidebook',
        )


def downgrade():
    for table in ('outings', 'outings_archives'):
        op.drop_column(table, 'disable_view_count', schema='guidebook')
