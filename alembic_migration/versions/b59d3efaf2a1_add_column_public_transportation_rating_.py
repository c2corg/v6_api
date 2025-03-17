"""Add column public_transportation_rating to route.py

Revision ID: b59d3efaf2a1
Revises: 626354ffcda0
Create Date: 2024-05-07 16:13:17.458223

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b59d3efaf2a1'
down_revision = '626354ffcda0'
branch_labels = None
depends_on = None


def upgrade():

    new_public_transportation_rating_type = sa.Enum(
        'good service',
        'seasonal service',
        'poor service',
        'nearby service',
        'unknown service',
        'no service',
        name='public_transportation_ratings',
        schema='guidebook'
    )
    new_public_transportation_rating_type.create(op.get_bind())
    op.alter_column(
        "waypoints",
        "public_transportation_rating",
        type_=new_public_transportation_rating_type,
        postgresql_using="public_transportation_rating::text::guidebook.public_transportation_ratings",
        schema="guidebook",
    )
    op.alter_column(
        'waypoints_archives',
        'public_transportation_rating',
        type_=new_public_transportation_rating_type,
        postgresql_using='public_transportation_rating::text::guidebook.public_transportation_ratings',
        schema='guidebook'
    )
    op.execute("DROP TYPE IF EXISTS guidebook.public_transportation_rating")
    op.add_column(
        'routes',
        sa.Column(
            'public_transportation_rating',
            new_public_transportation_rating_type,
            nullable=True),
        schema='guidebook')
    op.add_column(
        'routes_archives',
        sa.Column(
            'public_transportation_rating',
            new_public_transportation_rating_type,
            nullable=True),
        schema='guidebook')


def downgrade():
    op.drop_column('routes', 'public_transportation_rating', schema='guidebook')
    op.drop_column('routes_archives', 'public_transportation_rating', schema='guidebook')
    op.execute("UPDATE guidebook.waypoints SET public_transportation_rating = NULL WHERE public_transportation_rating = 'unknown service'")
    op.execute("UPDATE guidebook.waypoints_archives SET public_transportation_rating = NULL WHERE public_transportation_rating = 'unknown service'")
    new_public_transportation_rating_type = sa.Enum(
        'good service',
        'seasonal service',
        'poor service',
        'nearby service',
        'unknown service',
        'no service',
        name='public_transportation_rating',
        schema='guidebook'
    )
    new_public_transportation_rating_type.create(op.get_bind())
    op.alter_column(
        'waypoints',
        'public_transportation_rating',
        type_=new_public_transportation_rating_type,
        postgresql_using='public_transportation_rating::text::guidebook.public_transportation_rating',
        schema='guidebook'
    )
    op.alter_column(
        'waypoints_archives',
        'public_transportation_rating',
        type_=new_public_transportation_rating_type,
        postgresql_using='public_transportation_rating::text::guidebook.public_transportation_rating',
        schema='guidebook'
    )
    op.execute("DROP TYPE IF EXISTS guidebook.public_transportation_ratings")
