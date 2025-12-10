"""Add coverages

Revision ID: 335e0bc4df28
Revises: 6b40cb9c7c3d
Create Date: 2025-11-18 14:15:26.377504

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '335e0bc4df28'
down_revision = '6b40cb9c7c3d'
branch_labels = None
depends_on = None

def upgrade():
    coverage_type = sa.Enum('fr-idf', 'fr-ne', 'fr-nw', 'fr-se', 'fr-sw', name='coverage_type', schema='guidebook')
    op.create_table('coverages',
    sa.Column('coverage_type', coverage_type, nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('coverages_archives',
    sa.Column('coverage_type', coverage_type, nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )


def downgrade():
    op.drop_table('coverages_archives', schema='guidebook')
    op.drop_table('coverages', schema='guidebook')
    sa.Enum('fr-idf', 'fr-ne', 'fr-nw', 'fr-se', 'fr-sw', name='coverage_type', schema='guidebook').drop(op.get_bind())
