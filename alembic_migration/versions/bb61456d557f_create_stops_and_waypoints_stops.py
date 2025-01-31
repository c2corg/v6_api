from alembic import op
import sqlalchemy as sa

# Identifiant de la migration (modifié automatiquement par Alembic)
revision = "bb61456d557f"
down_revision = "626354ffcda0"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "stops",
        sa.Column("document_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        schema="guidebook"
    )

    op.create_table(
        "waypoints_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("waypoint_id", sa.Integer(), sa.ForeignKey("guidebook.waypoints.document_id")),
        sa.Column("stop_id", sa.Integer(), sa.ForeignKey("guidebook.stops.document_id")),  
        schema="guidebook"
    )

def downgrade():
    op.drop_table("waypoints_stops", schema="guidebook")

    op.drop_table("stops", schema="guidebook")
