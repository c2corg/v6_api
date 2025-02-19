from alembic import op
import sqlalchemy as sa

# Identifiant de la migration (modifié automatiquement par Alembic)
revision = "bb61456d557f"
down_revision = "626354ffcda0"
branch_labels = None
depends_on = None

def upgrade():
    # Créer la table stops
    op.create_table('stops',
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('stop_name', sa.String(), nullable=False),
        sa.Column('line', sa.String(), nullable=False),
        sa.Column('operator', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.PrimaryKeyConstraint('document_id'),
        schema='guidebook'
    )

    # Créer la table waypoints_stops (table de jointure many-to-many)
    op.create_table('waypoints_stops',
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('stop_id', sa.Integer(), nullable=False),
        sa.Column('waypoint_id', sa.Integer(), nullable=False),
        sa.Column('distance', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.ForeignKeyConstraint(['stop_id'], ['guidebook.stops.document_id'], name='fk_waypoint_stop_stop_id', use_alter=True),
        sa.ForeignKeyConstraint(['waypoint_id'], ['guidebook.waypoints.document_id'], name='fk_waypoint_stop_waypoint_id', use_alter=True),
        sa.PrimaryKeyConstraint('document_id', 'stop_id', 'waypoint_id'),  
        schema='guidebook'
    )


def downgrade():
    op.drop_table('waypoints_stops', schema='guidebook')
    op.drop_table('stops', schema='guidebook')
