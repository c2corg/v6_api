"""Update public_transportation_types

Revision ID: d4d360ef69bc
Revises: 6d64a7fbdb8b
Create Date: 2017-07-10 16:17:32.295441

"""
from alembic import op
import sqlalchemy as sa

from alembic_migration.extensions import drop_enum
from sqlalchemy.sql.expression import and_, any_, cast
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Table, MetaData

from c2corg_api.models.utils import ArrayOfEnum


# revision identifiers, used by Alembic.
revision = 'd4d360ef69bc'
down_revision = '6d64a7fbdb8b'
branch_labels = None
depends_on = None

def upgrade():
    old_options = ('train', 'bus', 'service_on_demand', 'boat', 'cable_car')
    new_options = ('train', 'bus', 'service_on_demand', 'boat')

    old_type = sa.Enum(
        *old_options, name='public_transportation_type', schema='guidebook')
    new_type = sa.Enum(
        *new_options, name='public_transportation_type_', schema='guidebook')
    new_type.create(op.get_bind(), checkfirst=False)

    # Create new column with temporary name
    op.add_column(
        'waypoints',
        sa.Column('public_transportation_types_', ArrayOfEnum(new_type)),
        schema='guidebook')

    op.add_column(
        'waypoints_archives',
        sa.Column('public_transportation_types_', ArrayOfEnum(new_type)),
        schema='guidebook')

    # Create temporary string col for array types converting
    op.add_column(
        'waypoints',
        sa.Column('public_transportation_types_str', sa.String),
        schema='guidebook')

    op.add_column(
        'waypoints_archives',
        sa.Column('public_transportation_types_str', sa.String),
        schema='guidebook')

    waypoints = Table(
        'waypoints',
        MetaData(),
        sa.Column('lift_access', sa.Boolean),
        sa.Column('public_transportation_types', ArrayOfEnum(old_type)),
        sa.Column('public_transportation_types_', ArrayOfEnum(new_type)),
        sa.Column('public_transportation_types_str', sa.String),
        schema='guidebook')
    # For waypoints having 'cable_car' in public_transportation_types:
    # * set the lift_access flag to true
    # * remove 'cable_car' from public_transportation_types
    op.execute(
        waypoints.update(). \
        where(and_(
            waypoints.c.public_transportation_types != None,
            any_(waypoints.c.public_transportation_types)==op.inline_literal('cable_car')
        )). \
        values({
            'lift_access': True,
            'public_transportation_types': func.array_remove(
                waypoints.c.public_transportation_types, 'cable_car')
        })
    )
    # Then fill the new public_transportation_types_ col with values
    # from public_transportation_types. The intermediary string conversion
    # is needed because it is not possible to directly cast from one array
    # type to another.
    op.execute(
        waypoints.update(). \
        where(waypoints.c.public_transportation_types != None). \
        values({
            'public_transportation_types_str': func.array_to_string(
                waypoints.c.public_transportation_types, ',')
        })
    )
    op.execute(
        waypoints.update(). \
        where(waypoints.c.public_transportation_types != None). \
        values({
            'public_transportation_types_': cast(func.string_to_array(
                waypoints.c.public_transportation_types_str, ','), ArrayOfEnum(new_type))
        })
    )

    # Same for archives data
    archives = Table(
        'waypoints_archives',
        MetaData(),
        sa.Column('lift_access', sa.Boolean),
        sa.Column('public_transportation_types', ArrayOfEnum(old_type)),
        sa.Column('public_transportation_types_', ArrayOfEnum(new_type)),
        sa.Column('public_transportation_types_str', sa.String),
        schema='guidebook')
    op.execute(
        archives.update(). \
        where(and_(
            archives.c.public_transportation_types != None,
            any_(archives.c.public_transportation_types)==op.inline_literal('cable_car')
        )). \
        values({
            'lift_access': True,
            'public_transportation_types': func.array_remove(
                archives.c.public_transportation_types, 'cable_car')
        })
    )
    op.execute(
        archives.update(). \
        where(archives.c.public_transportation_types != None). \
        values({
            'public_transportation_types_str': func.array_to_string(
                archives.c.public_transportation_types, ',')
        })
    )
    op.execute(
        archives.update(). \
        where(archives.c.public_transportation_types != None). \
        values({
            'public_transportation_types_': cast(func.string_to_array(
                archives.c.public_transportation_types_str, ','), ArrayOfEnum(new_type))
        })
    )

    # Drop old column and enum
    op.drop_column('waypoints', 'public_transportation_types', schema='guidebook')
    op.drop_column('waypoints_archives', 'public_transportation_types', schema='guidebook')
    op.drop_column('waypoints', 'public_transportation_types_str', schema='guidebook')
    op.drop_column('waypoints_archives', 'public_transportation_types_str', schema='guidebook')
    drop_enum('public_transportation_type', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.public_transportation_type_ RENAME TO public_transportation_type')

    # Rename column
    op.alter_column(
        'waypoints',
        'public_transportation_types_',
        new_column_name='public_transportation_types',
        schema='guidebook')

    op.alter_column(
        'waypoints_archives',
        'public_transportation_types_',
        new_column_name='public_transportation_types',
        schema='guidebook')


def downgrade():
    # Not possible to restore removed 'cable_car' values
    pass
