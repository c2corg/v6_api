"""Improve SERAC database

Revision ID: 06d2a35e39c8
Revises: 85a5ed3c76a8
Create Date: 2019-12-09 13:24:15.936753

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.schema import Table, MetaData
from alembic_migration.extensions import drop_enum
import csv
from c2corg_api.models.utils import ArrayOfEnum

# revision identifiers, used by Alembic.
revision = '06d2a35e39c8'
down_revision = '85a5ed3c76a8'
branch_labels = None
depends_on = None


key_map = {
    b'avalanche': 'avalanche',
    b'd\xc3\xa9s\xc3\xa9quilibre/chute ': 'person_fall',
    b'chute de pierre/glace/serac': 'stone_ice_fall',
    b'chute en crevasse, b\xc3\xa9di\xc3\xa8re ': 'crevasse_fall',
    b'man\xc5\x93uvre de s\xc3\xa9cu ': 'safety_operation',
    b'd\xc3\xa9faillanche physique non traumatique': 'physical_failure',
    b'\xc3\xa9v\xc3\xa8nement m\xc3\xa9t\xc3\xa9o': 'weather_event',
    b'autre': 'other',
    b'effondrement cascade': 'ice_cornice_collapse',
    b'l\xc3\xa9sion sans chute ': 'injury_without_fall',
    b'personne bloqu\xc3\xa9e': 'blocked_person'
}



def upgrade():

    # convert activities
    activity_conversions = [
        ('hiking', 'other'),
        ('snowshoeing', 'other'),
        ('paragliding', 'other'),
        ('mountain_biking', 'other'),
        ('via_ferrata', 'other'),
        ('slacklining', 'other'),
        ('skitouring', 'skitouring'),
        ('snow_ice_mixed', 'snow_ice_mixed'),
        ('mountain_climbing', 'alpine_climbing'),
        ('rock_climbing', 'sport_climbing'),
        ('ice_climbing', 'ice_climbing'),
    ]
    old_activity_type = ArrayOfEnum(
        sa.Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing',
                'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing',
                'paragliding', 'mountain_biking', 'via_ferrata', 'slacklining',
                name='activity_type', schema='guidebook')
    )
    new_activity_type = sa.Enum('sport_climbing', 'multipitch_climbing',
                                'alpine_climbing', 'snow_ice_mixed',
                                'ice_climbing', 'skitouring', 'other',
                                name='event_activity_type', schema='guidebook')
    new_activity_type.create(op.get_bind())
    op.add_column('xreports',
                  sa.Column('event_activity', new_activity_type),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('event_activity', new_activity_type),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('activities', old_activity_type),
               sa.Column('event_activity', new_activity_type, nullable=True),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('activities', old_activity_type),
                sa.Column('event_activity', new_activity_type, nullable=True),
                schema='guidebook')
    for (old_value, new_value) in activity_conversions:
        op.execute(xr.update()
                   .where(xr.c.activities.contains(sa.literal([old_value])
                                                   .cast(old_activity_type)))
                   .values(event_activity=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.activities.contains(sa.literal([old_value])
                                                    .cast(old_activity_type)))
                   .values(event_activity=op.inline_literal(new_value)))

    op.alter_column('xreports', 'event_activity',
                    nullable=False, schema='guidebook')
    op.alter_column('xreports_archives', 'event_activity',
                    nullable=False, schema='guidebook')

    op.drop_column('xreports', 'activities', schema='guidebook')
    op.drop_column('xreports_archives', 'activities', schema='guidebook')

    # end of activities conversion

    # convert types
    type_conversions = [
        ('avalanche', 'avalanche'),
        ('stone_fall', 'stone_ice_fall'),
        ('falling_ice', 'stone_ice_fall'),
        ('person_fall', 'person_fall'),
        ('crevasse_fall', 'crevasse_fall'),
        ('roped_fall', 'person_fall'),
        ('physical_failure', 'physical_failure'),
        ('lightning', 'weather_event'),
        ('other', 'other')
    ]
    old_event_type = ArrayOfEnum(
        sa.Enum('avalanche', 'stone_fall', 'falling_ice', 'person_fall',
                'crevasse_fall', 'roped_fall', 'physical_failure',
                'lightning', 'other',
                name='event_type', schema='guidebook')
    )
    new_event_type = sa.Enum(
        'avalanche', 'stone_ice_fall', 'ice_cornice_collapse',
        'person_fall', 'crevasse_fall', 'physical_failure',
        'injury_without_fall', 'blocked_person', 'weather_event',
        'safety_operation', 'critical_situation', 'other',
        name='event_type_', schema='guidebook'
    )
    new_event_type.create(op.get_bind())
    op.add_column('xreports',
                  sa.Column('event_type_', new_event_type),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('event_type_', new_event_type),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('event_type', old_event_type),
               sa.Column('event_type_', new_event_type),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('event_type', old_event_type),
                sa.Column('event_type_', new_event_type),
                schema='guidebook')
    for (old_value, new_value) in type_conversions:
        op.execute(xr.update()
                   .where(xr.c.event_type.contains(sa.literal([old_value])
                                                   .cast(old_event_type)))
                   .values(event_type_=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.event_type.contains(sa.literal([old_value])
                                                    .cast(old_event_type)))
                   .values(event_type_=op.inline_literal(new_value)))

    op.alter_column('xreports', 'event_type',
                    nullable=False, schema='guidebook')
    op.alter_column('xreports_archives', 'event_type',
                    nullable=False, schema='guidebook')

    op.drop_column('xreports', 'event_type', schema='guidebook')
    op.drop_column('xreports_archives', 'event_type', schema='guidebook')
    drop_enum('event_type', schema='guidebook')
    op.execute('ALTER TYPE guidebook.event_type_ RENAME TO event_type')
    op.alter_column(
        'xreports',
        'event_type_',
        new_column_name='event_type',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'event_type_',
        new_column_name='event_type',
        schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('document_id', sa.types.INTEGER),
               sa.Column('event_type', new_event_type),
               schema='guidebook')
    # xra = Table('xreports_archives', MetaData(),
    #             sa.Column('document_id', sa.types.INTEGER),
    #             sa.Column('event_type', new_event_type),
    #             schema='guidebook')
    try:
        with open('./alembic_migration/versions/06d2a35e39c8_improve_serac_database_data.csv') as f:
            rr = csv.reader(f)
            header = rr.__next__()
            assert (header[1] == 'Document') and (header[8] == 'ENS principal')
            for line in rr:
                print("update {} -> {}".format(line[1],
                                               key_map[line[8].lower().encode()]))
                op.execute(xr.update()
                           .where(xr.c.document_id == line[1])
                           .values(event_type=key_map[line[8].lower().encode()]))
                # op.execute(xra.update()
                #            .where(xra.c.document_id == line[1])
                #            .values(event_type=key_map[line[8].lower()]))
    except Exception as e:
        print("EXCEPT!!! {} {}".format(type(e), e))
    # end of types conversion

    # convert autonomy enum
    autonomy_conversions = [
        ('non_autonomous', 'non_autonomous'),
        ('autonomous', 'autonomous'),
        ('initiator', 'autonomous'),
        ('expert', 'expert')
    ]
    old_autonomy_type = sa.Enum('non_autonomous', 'autonomous', 'initiator', 'expert', name='autonomy', schema='guidebook')
    new_autonomy_type = sa.Enum('non_autonomous', 'autonomous', 'expert', name='autonomy_', schema='guidebook')
    new_autonomy_type.create(op.get_bind())
    # op.alter_column('xreports', 'autonomy',
    #                 type_=new_autonomy_type,
    #                 existing_type=old_autonomy_type,
    #                 schema='guidebook')
    # does not allow automatic casting if table not empty

    op.add_column('xreports',
                  sa.Column('autonomy_', new_autonomy_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('autonomy_', new_autonomy_type, nullable=True),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('autonomy', old_autonomy_type),
               sa.Column('autonomy_', new_autonomy_type, nullable=True),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('autonomy', old_autonomy_type),
                sa.Column('autonomy_', new_autonomy_type, nullable=True),
                schema='guidebook')
    for (old_value, new_value) in autonomy_conversions:
        op.execute(xr.update()
                   .where(xr.c.autonomy == op.inline_literal(old_value))
                   .values(autonomy_=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.autonomy == op.inline_literal(old_value))
                   .values(autonomy_=op.inline_literal(new_value)))

    op.drop_column('xreports', 'autonomy', schema='guidebook')
    op.drop_column('xreports_archives', 'autonomy', schema='guidebook')
    # op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('autonomy', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.autonomy_ RENAME TO autonomy')

    # Rename column
    op.alter_column(
        'xreports',
        'autonomy_',
        new_column_name='autonomy',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'autonomy_',
        new_column_name='autonomy',
        schema='guidebook')

    # end of autonomy conversion

    # convert activity enum
    activity_conversions = [
        ('activity_rate_150', 'activity_rate_w1'),
        ('activity_rate_50', 'activity_rate_w1'),
        ('activity_rate_30', 'activity_rate_m2'),
        ('activity_rate_20', 'activity_rate_m2'),
        ('activity_rate_10', 'activity_rate_y5'),
        ('activity_rate_5', 'activity_rate_y5'),
        ('activity_rate_1', 'activity_rate_y5')
    ]
    old_activity_type = sa.Enum('activity_rate_150', 'activity_rate_50',
                                'activity_rate_30', 'activity_rate_20',
                                'activity_rate_10', 'activity_rate_5',
                                'activity_rate_1',
                                name='activity_rate', schema='guidebook')
    new_activity_type = sa.Enum('activity_rate_y5', 'activity_rate_m2',
                                'activity_rate_w1',
                                name='activity_rate_', schema='guidebook')
    new_activity_type.create(op.get_bind())

    op.add_column('xreports',
                  sa.Column('activity_rate_', new_activity_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('activity_rate_', new_activity_type, nullable=True),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('activity_rate', old_activity_type),
               sa.Column('activity_rate_', new_activity_type, nullable=True),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('activity_rate', old_activity_type),
                sa.Column('activity_rate_', new_activity_type, nullable=True),
                schema='guidebook')
    for (old_value, new_value) in activity_conversions:
        op.execute(xr.update()
                   .where(xr.c.activity_rate == op.inline_literal(old_value))
                   .values(activity_rate_=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.activity_rate == op.inline_literal(old_value))
                   .values(activity_rate_=op.inline_literal(new_value)))

    op.drop_column('xreports', 'activity_rate', schema='guidebook')
    op.drop_column('xreports_archives', 'activity_rate', schema='guidebook')
    # op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('activity_rate', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.activity_rate_ RENAME TO activity_rate')

    # Rename column
    op.alter_column(
        'xreports',
        'activity_rate_',
        new_column_name='activity_rate',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'activity_rate_',
        new_column_name='activity_rate',
        schema='guidebook')

    # end of activity conversion

    op.drop_column('xreports', 'nb_outings', schema='guidebook')
    op.drop_column('xreports_archives', 'nb_outings', schema='guidebook')
    # op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('nb_outings', schema='guidebook')

    supervision_type = sa.Enum('no_supervision', 'federal_supervision',
                               'professional_supervision',
                               name='supervision_type', schema='guidebook')
    supervision_type.create(op.get_bind())
    op.add_column('xreports', sa.Column('supervision', supervision_type,
                                        nullable=True), schema='guidebook')
    op.add_column('xreports_archives', sa.Column('supervision', supervision_type,
                                                 nullable=True), schema='guidebook')

    qualification_type = sa.Enum('federal_supervisor', 'federal_trainer',
                                 'professional_diploma',
                                 name='qualification_type', schema='guidebook')
    qualification_type.create(op.get_bind())
    op.add_column('xreports', sa.Column('qualification', qualification_type,
                                        nullable=True), schema='guidebook')
    op.add_column('xreports_archives', sa.Column('qualification', qualification_type,
                                                 nullable=True), schema='guidebook')


def downgrade():

    # convert activity enum
    activity_conversions = [
        ('activity_rate_w1', 'activity_rate_50'),
        ('activity_rate_m2', 'activity_rate_20'),
        ('activity_rate_y5', 'activity_rate_10'),
        ('activity_rate_y5', 'activity_rate_5'),
    ]
    old_activity_type = sa.Enum('activity_rate_y5', 'activity_rate_m2', 'activity_rate_w1', name='activity_rate', schema='guidebook')
    new_activity_type = sa.Enum('activity_rate_150', 'activity_rate_50', 'activity_rate_30', 'activity_rate_20', 'activity_rate_10',
                                'activity_rate_5', 'activity_rate_1', name='activity_rate_', schema='guidebook')
    new_activity_type.create(op.get_bind())

    op.add_column('xreports',
                  sa.Column('activity_rate_', new_activity_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('activity_rate_', new_activity_type, nullable=True),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('activity_rate', old_activity_type),
               sa.Column('activity_rate_', new_activity_type, nullable=True),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('activity_rate', old_activity_type),
                sa.Column('activity_rate_', new_activity_type, nullable=True),
                schema='guidebook')
    for (old_value, new_value) in activity_conversions:
        op.execute(xr.update()
                   .where(xr.c.activity_rate == op.inline_literal(old_value))
                   .values(activity_rate_=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.activity_rate == op.inline_literal(old_value))
                   .values(activity_rate_=op.inline_literal(new_value)))

    op.drop_column('xreports', 'activity_rate', schema='guidebook')
    op.drop_column('xreports_archives', 'activity_rate', schema='guidebook')
    # op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('activity_rate', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.activity_rate_ RENAME TO activity_rate')

    # Rename column
    op.alter_column(
        'xreports',
        'activity_rate_',
        new_column_name='activity_rate',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'activity_rate_',
        new_column_name='activity_rate',
        schema='guidebook')

    # end of activity conversion

    # convert autonomy enum
    autonomy_conversions = [
        ('non_autonomous', 'non_autonomous'),
        ('autonomous', 'autonomous'),
        ('expert', 'expert')
    ]
    old_autonomy_type = sa.Enum('non_autonomous', 'autonomous', 'expert', name='autonomy', schema='guidebook')
    new_autonomy_type = sa.Enum('non_autonomous', 'autonomous', 'initiator', 'expert', name='autonomy_', schema='guidebook')
    new_autonomy_type.create(op.get_bind())
    # op.alter_column('xreports', 'autonomy',
    #                 type_=new_autonomy_type,
    #                 existing_type=old_autonomy_type,
    #                 schema='guidebook')
    # does not allow automatic casting if table not empty

    op.add_column('xreports',
                  sa.Column('autonomy_', new_autonomy_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('autonomy_', new_autonomy_type, nullable=True),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('autonomy', old_autonomy_type),
               sa.Column('autonomy_', new_autonomy_type, nullable=True),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('autonomy', old_autonomy_type),
                sa.Column('autonomy_', new_autonomy_type, nullable=True),
                schema='guidebook')
    for (old_value, new_value) in autonomy_conversions:
        op.execute(xr.update()
                   .where(xr.c.autonomy == op.inline_literal(old_value))
                   .values(autonomy_=op.inline_literal(new_value)))
        op.execute(xra.update()
                   .where(xra.c.autonomy == op.inline_literal(old_value))
                   .values(autonomy_=op.inline_literal(new_value)))

    op.drop_column('xreports', 'autonomy', schema='guidebook')
    op.drop_column('xreports_archives', 'autonomy', schema='guidebook')
    # op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('autonomy', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.autonomy_ RENAME TO autonomy')

    # Rename column
    op.alter_column(
        'xreports',
        'autonomy_',
        new_column_name='autonomy',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'autonomy_',
        new_column_name='autonomy',
        schema='guidebook')

    # end of autonomy conversion

    op.drop_column('xreports', 'supervision', schema='guidebook')
    op.drop_column('xreports_archives', 'supervision', schema='guidebook')
    drop_enum('supervision_type', schema='guidebook')
    op.drop_column('xreports', 'qualification', schema='guidebook')
    op.drop_column('xreports_archives', 'qualification', schema='guidebook')
    drop_enum('qualification_type', schema='guidebook')

    nb_outing_type = sa.Enum('nb_outings_4', 'nb_outings_9', 'nb_outings_14', 'nb_outings_15', name='nb_outings', schema='guidebook')
    nb_outing_type.create(op.get_bind())
    op.add_column('xreports',
                  sa.Column('nb_outings', nb_outing_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('nb_outings', nb_outing_type, nullable=True),
                  schema='guidebook')

    activity_conversions = [
        ('other', 'hiking'),
        ('skitouring', 'skitouring'),
        ('snow_ice_mixed', 'snow_ice_mixed'),
        ('alpine_climbing', 'mountain_climbing'),
        ('sport_climbing', 'rock_climbing'),
        ('ice_climbing', 'ice_climbing')
    ]
    old_activity_type = sa.Enum('sport_climbing', 'multipitch_climbing',
                                'alpine_climbing', 'snow_ice_mixed',
                                'ice_climbing', 'skitouring', 'other',
                                name='event_activity_type', schema='guidebook')

    activities_type = ArrayOfEnum(
        sa.Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing',
                'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing',
                'paragliding', 'mountain_biking', 'via_ferrata', 'slacklining',
                name='activity_type', schema='guidebook')
    )
    op.add_column('xreports',
                  sa.Column('activities', activities_type, nullable=True),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('activities', activities_type, nullable=True),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('activities', activities_type, nullable=True),
               sa.Column('event_activity', old_activity_type),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('activities', activities_type, nullable=True),
                sa.Column('event_activity', old_activity_type),
                schema='guidebook')
    for (old_value, new_value) in activity_conversions:
        op.execute(xr.update()
                   .where(xr.c.event_activity == op.inline_literal(old_value))
                   .values(activities=sa.literal([new_value])))
        op.execute(xra.update()
                   .where(xra.c.event_activity == op.inline_literal(old_value))
                   .values(activities=sa.literal([new_value])))

    op.alter_column('xreports', 'activities',
                    nullable=False, schema='guidebook')
    op.alter_column('xreports_archives', 'activities',
                    nullable=False, schema='guidebook')

    op.drop_column('xreports', 'event_activity', schema='guidebook')
    op.drop_column('xreports_archives', 'event_activity', schema='guidebook')
    drop_enum('event_activity_type', schema='guidebook')


    # convert types
    type_conversions = [
        ('avalanche', 'avalanche'),
        ('stone_ice_fall', 'stone_fall'),
        ('ice_cornice_collapse', 'falling_ice'),
        ('person_fall', 'person_fall'),
        ('crevasse_fall', 'crevasse_fall'),
        ('physical_failure', 'physical_failure'),
        ('injury_without_fall', 'other'),
        ('blocked_person', 'other'),
        ('safety_operation', 'other'),
        ('critical_situation', 'other'),
        ('weather_event', 'lightning'),
        ('other', 'other')
    ]
    old_event_type = sa.Enum(
        'avalanche', 'stone_ice_fall', 'ice_cornice_collapse',
        'person_fall', 'crevasse_fall', 'physical_failure',
        'injury_without_fall', 'blocked_person', 'weather_event',
        'safety_operation', 'critical_situation', 'other',
        name='event_type', schema='guidebook'
    )
    new_event_type = sa.Enum(
        'avalanche', 'stone_fall', 'falling_ice', 'person_fall',
        'crevasse_fall', 'roped_fall', 'physical_failure',
        'lightning', 'other',
        name='event_type_', schema='guidebook'
    )
    new_event_type.create(op.get_bind())
    op.add_column('xreports',
                  sa.Column('event_type_', ArrayOfEnum(new_event_type)),
                  schema='guidebook')
    op.add_column('xreports_archives',
                  sa.Column('event_type_', ArrayOfEnum(new_event_type)),
                  schema='guidebook')

    xr = Table('xreports', MetaData(),
               sa.Column('event_type', old_event_type),
               sa.Column('event_type_', ArrayOfEnum(new_event_type)),
               schema='guidebook')
    xra = Table('xreports_archives', MetaData(),
                sa.Column('event_type', old_event_type),
                sa.Column('event_type_', ArrayOfEnum(new_event_type)),
                schema='guidebook')
    for (old_value, new_value) in type_conversions:
        op.execute(xr.update()
                   .where(xr.c.event_type == op.inline_literal(old_value))
                   .values(event_type_=sa.literal([new_value])))
        op.execute(xra.update()
                   .where(xra.c.event_type == op.inline_literal(old_value))
                   .values(event_type_=sa.literal([new_value])))

    op.drop_column('xreports', 'event_type', schema='guidebook')
    op.drop_column('xreports_archives', 'event_type', schema='guidebook')
    drop_enum('event_type', schema='guidebook')
    op.execute('ALTER TYPE guidebook.event_type_ RENAME TO event_type')
    op.alter_column(
        'xreports',
        'event_type_',
        new_column_name='event_type',
        schema='guidebook')
    op.alter_column(
        'xreports_archives',
        'event_type_',
        new_column_name='event_type',
        schema='guidebook')

    # end of types conversion
