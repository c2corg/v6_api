"""Add slacklining

Revision ID: bacd59c5806a
Revises: 91b1beed9a1c
Create Date: 2017-01-08 10:01:56.428713

"""
from alembic import op
import sqlalchemy as sa
from c2corg_api.models import utils
from alembic_migration.extensions import drop_enum
from sqlalchemy.sql.sqltypes import Enum

# revision identifiers, used by Alembic.
revision = 'bacd59c5806a'
down_revision = '91b1beed9a1c'
branch_labels = None
depends_on = None

# activity enum
activities_old = [
    'skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing',
    'ice_climbing', 'hiking', 'snowshoeing', 'paragliding',
    'mountain_biking', 'via_ferrata']
activities_new = activities_old + ['slacklining', ]

activity_enum_old = Enum(
    *activities_old,
    name='activity_type', schema='guidebook')
activity_enum_new = Enum(
    *activities_new,
    name='activity_type', schema='guidebook')
activity_enum_tmp = Enum(
    *activities_new,
    name='_activity_type', schema='guidebook')

tables_with_activity_column = [
    ('guidebook', 'articles', 'activities', False),
    ('guidebook', 'books', 'activities', False),
    ('guidebook', 'images', 'activities', False),
    ('guidebook', 'outings', 'activities', False),
    ('guidebook', 'routes', 'activities', False),
    ('guidebook', 'user_profiles', 'activities', False),
    ('guidebook', 'xreports', 'activities', False),
    ('guidebook', 'articles_archives', 'activities', False),
    ('guidebook', 'books_archives', 'activities', False),
    ('guidebook', 'images_archives', 'activities', False),
    ('guidebook', 'outings_archives', 'activities', False),
    ('guidebook', 'routes_archives', 'activities', False),
    ('guidebook', 'user_profiles_archives', 'activities', False),
    ('guidebook', 'xreports_archives', 'activities', False),
    ('guidebook', 'feed_document_changes', 'activities', True),
    ('users', 'user', 'feed_filter_activities', True),
]

# waypoint_type enum
waypoint_types_old = [
    'summit', 'pass', 'lake', 'waterfall', 'locality', 'bisse', 'canyon', 'access',
    'climbing_outdoor', 'climbing_indoor', 'hut', 'gite', 'shelter', 'bivouac',
    'camp_site', 'base_camp', 'local_product', 'paragliding_takeoff', 'paragliding_landing',
    'cave', 'waterpoint', 'weather_station', 'webcam', 'virtual', 'misc']
waypoint_types_new = waypoint_types_old + ['slackline_spot', ]

waypoint_enum_old = Enum(
    *waypoint_types_old,
    name='waypoint_type', schema='guidebook')
waypoint_enum_new = Enum(
    *waypoint_types_new,
    name='waypoint_type', schema='guidebook')
waypoint_enum_tmp = Enum(
    *waypoint_types_new,
    name='_waypoint_type', schema='guidebook')

tables_with_waypoint_type_column = [
    ('guidebook', 'waypoints', 'waypoint_type', False),
    ('guidebook', 'waypoints_archives', 'waypoint_type', False),
]


def replace_enum(old_enum, new_enum, tmp_enum, tables_to_update, array_column):
    """ Function to replace an old enum with a new enum, e.g. to add a new
     value to an enum.
     See: http://stackoverflow.com/a/14845740/119937
    """
    # Create a temporary type, convert and drop the "old" type
    tmp_enum.create(op.get_bind(), checkfirst=False)

    for schema, table, column, update_default in tables_to_update:
        if array_column and update_default:
            op.execute(
                'ALTER TABLE {0}.{1} ALTER COLUMN {2} DROP DEFAULT'.format(
                    schema, table, column))

        op.execute(
            'ALTER TABLE {0}.{1} ALTER COLUMN {2} TYPE {3}.{4}{5}'
            ' USING {2}::text{5}::{3}.{4}{5}'.format(
                schema, table, column, tmp_enum.schema, tmp_enum.name,
                '[]' if array_column else ''))

    old_enum.drop(op.get_bind(), checkfirst=False)

    # Create and convert to the "new" type
    new_enum.create(op.get_bind(), checkfirst=False)

    for schema, table, column, update_default in tables_to_update:
        op.execute(
            'ALTER TABLE {0}.{1} ALTER COLUMN {2} TYPE {3}.{4}{5}'
            ' USING {2}::text{5}::{3}.{4}{5}'.format(
                schema, table, column, new_enum.schema, new_enum.name,
                '[]' if array_column else ''))

        if array_column and update_default:
            op.execute(
                'ALTER TABLE {0}.{1} ALTER COLUMN {2} '
                'SET DEFAULT \'{{}}\'::{3}.{4}[]'.format(
                    schema, table, column, new_enum.schema, new_enum.name))

    tmp_enum.drop(op.get_bind(), checkfirst=False)


def upgrade():
    # add new value 'slackline_spot' to enum 'waypoint_type'
    replace_enum(
        waypoint_enum_old, waypoint_enum_new, waypoint_enum_tmp,
        tables_with_waypoint_type_column, array_column=False)

    # add new value 'slacklining' to enum 'activity_type'
    replace_enum(
        activity_enum_old, activity_enum_new, activity_enum_tmp,
        tables_with_activity_column, array_column=True)

    # new enum 'slackline_type'
    slackline_type_enum = sa.Enum(
        'slackline', 'highline', 'waterline',
        name='slackline_type', schema='guidebook')

    op.execute("""
        CREATE TYPE guidebook.slackline_type
        AS ENUM('slackline', 'highline', 'waterline');
        """)

    for table in ['routes', 'routes_archives']:
        op.add_column(
            table,
            sa.Column('slackline_type', slackline_type_enum),
            schema='guidebook')
        op.add_column(
            table,
            sa.Column('slackline_height', sa.SmallInteger),
            schema='guidebook')

    for table in ['routes_locales', 'routes_locales_archives']:
        op.add_column(
            table,
            sa.Column('slackline_anchor1', sa.String),
            schema='guidebook')
        op.add_column(
            table,
            sa.Column('slackline_anchor2', sa.String),
            schema='guidebook')

    for table in ['waypoints', 'waypoints_archives']:
        op.add_column(
            table,
            sa.Column(
                'slackline_types', utils.ArrayOfEnum(slackline_type_enum)),
            schema='guidebook')
        op.add_column(
            table,
            sa.Column('slackline_length_min', sa.SmallInteger),
            schema='guidebook')
        op.add_column(
            table,
            sa.Column('slackline_length_max', sa.SmallInteger),
            schema='guidebook')


def downgrade():
    # remove value 'slacklining' from enum 'activity_type' and 'slackline_spot'
    # from 'waypoint_type'
    # note that this operation will fail if the value is still used somewhere.
    replace_enum(
        activity_enum_new, activity_enum_old, activity_enum_tmp,
        tables_with_activity_column, array_column=True)
    replace_enum(
        waypoint_enum_new, waypoint_enum_old, waypoint_enum_tmp,
        tables_with_waypoint_type_column, array_column=False)

    for table in ['routes', 'routes_archives']:
        op.drop_column(table, 'slackline_type', schema='guidebook')
        op.drop_column(table, 'slackline_height', schema='guidebook')

    for table in ['routes_locales', 'routes_locales_archives']:
        op.drop_column(table, 'slackline_anchor1', schema='guidebook')
        op.drop_column(table, 'slackline_anchor2', schema='guidebook')

    for table in ['waypoints', 'waypoints_archives']:
        op.drop_column(table, 'slackline_types', schema='guidebook')
        op.drop_column(table, 'slackline_length_min', schema='guidebook')
        op.drop_column(table, 'slackline_length_max', schema='guidebook')

    drop_enum('slackline_type', schema='guidebook')
