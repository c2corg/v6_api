from alembic import op
import sqlalchemy as sa

# Identifiant de la migration (modifié automatiquement par Alembic)
revision = "bb61456d557f"
down_revision = "626354ffcda0"
branch_labels = None
depends_on = None

def upgrade():
    # Créer la table stopareas
    op.create_table('stopareas',
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('navitia_id', sa.String(), nullable=False),
        sa.Column('stoparea_name', sa.String(), nullable=False),
        sa.Column('line', sa.String(), nullable=False),
        sa.Column('operator', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.PrimaryKeyConstraint('document_id'),
        schema='guidebook'
    )

    # Créer la table waypoints_stopareas (table de jointure many-to-many)
    op.create_table('waypoints_stopareas',
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('stoparea_id', sa.Integer(), nullable=False),
        sa.Column('waypoint_id', sa.Integer(), nullable=False),
        sa.Column('distance', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.ForeignKeyConstraint(['stoparea_id'], ['guidebook.stopareas.document_id'], name='fk_waypoint_stoparea_stoparea_id', use_alter=True),
        sa.ForeignKeyConstraint(['waypoint_id'], ['guidebook.waypoints.document_id'], name='fk_waypoint_stoparea_waypoint_id', use_alter=True),
        sa.PrimaryKeyConstraint('document_id', 'stoparea_id', 'waypoint_id'),  
        schema='guidebook'
    )


def downgrade():
    op.drop_table('waypoints_stopareas', schema='guidebook')
    op.drop_table('stopareas', schema='guidebook')
