"""Create stops and waypoints stops

Revision ID: bb61456d557f
Revises: b59d3efaf2a1
Create Date: 2025-01-31 11:47:00.000000

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2

# revision identifiers, used by Alembic.
revision = "bb61456d557f"
down_revision = "b59d3efaf2a1"
branch_labels = None
depends_on = None

def upgrade():
    # stopareas
    op.create_table('stopareas',
        sa.Column('stoparea_id', sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column('navitia_id', sa.String(), nullable=False),
        sa.Column('stoparea_name', sa.String(), nullable=False),
        sa.Column('line', sa.String(), nullable=False),
        sa.Column('operator', sa.String(), nullable=False),
        sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=3857, management=True), nullable=True),
        schema='guidebook'
    )

    # waypoints_stopareas
    op.create_table(
        'waypoints_stopareas',
        sa.Column('waypoint_stoparea_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('stoparea_id', sa.Integer(), nullable=False),
        sa.Column('waypoint_id', sa.Integer(), nullable=False),
        sa.Column('distance', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['stoparea_id'], ['guidebook.stopareas.stoparea_id'], name='fk_waypoint_stoparea_stoparea_id', use_alter=True),
        sa.ForeignKeyConstraint(['waypoint_id'], ['guidebook.waypoints.document_id'], name='fk_waypoint_stoparea_waypoint_id', use_alter=True),
        sa.UniqueConstraint('stoparea_id', 'waypoint_id', name='uq_waypoints_stopareas'),
        schema='guidebook'
    )



def downgrade():
    op.drop_table('waypoints_stopareas', schema='guidebook')
    op.drop_table('stopareas', schema='guidebook')
