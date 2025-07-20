from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6b40cb9c7c3d"
down_revision = "bb61456d557f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('routes',
        sa.Column('calculated_duration', sa.Float(), nullable=True),
        schema='guidebook'
    )
    op.add_column('routes_archives',
            sa.Column('calculated_duration', sa.Float(), nullable=True),
            schema='guidebook'
        )


def downgrade():
    op.drop_column('routes', 'calculated_duration', schema='guidebook')
    op.drop_column('routes_archives', 'calculated_duration', schema='guidebook')