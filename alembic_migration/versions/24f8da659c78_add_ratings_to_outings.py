"""Add ratings to outings

Revision ID: 24f8da659c78
Revises: 8c230a4a0284
Create Date: 2017-10-13 14:05:52.606170

"""
from os.path import join, dirname
import codecs
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '24f8da659c78'
down_revision = '077ddf78a1f3'
branch_labels = None
depends_on = None

metadata = sa.MetaData()

ll = sa.Table('history_metadata', metadata,
              sa.Column('id', sa.Integer, primary_key=True),
              sa.Column('user_id', sa.Integer),
              sa.Column('comment', sa.Unicode(256)),
              sa.Column('written_at', sa.DateTime(timezone=True)),
              schema='guidebook')


outings_table = sa.Table(
    'outings', metadata,
    sa.Column('document_id', sa.Integer, primary_key=True),
    sa.Column('ski_rating', sa.Unicode(256)),
    sa.Column('labande_global_rating', sa.Unicode(256)),
    sa.Column('global_rating', sa.Unicode(256)),
    sa.Column('snowshoe_rating', sa.Unicode(256)),
    sa.Column('hiking_rating', sa.Unicode(256)),
    sa.Column('height_diff_difficulties', sa.Unicode(256)),
    sa.Column('engagement_rating', sa.Unicode(256)),
    sa.Column('equipment_rating', sa.Unicode(256)),
    sa.Column('rock_free_rating', sa.Unicode(256)),
    sa.Column('ice_rating', sa.Unicode(256)),
    sa.Column('via_ferrata_rating', sa.Unicode(256)),
    sa.Column('mtb_up_rating', sa.Unicode(256)),
    sa.Column('mtb_down_rating', sa.Unicode(256)),
    schema='guidebook')


update_text = 'Automatically adding ratings to outings from associated routes'
update_tables = ['outings', 'outings_archives']


def upgrade():
    # For info:
    #     activities_dict = {
    #         'skitouring': ['ski_rating', 'labande_global_rating'
    #                        ],
    #         'snowshoing': ['snowshoe_rating'],
    #         'hiking': ['hiking_rating'],
    #         'snow_ice_mixed': [
    #             'global_rating', 'height_diff_difficulties',
    #             'engagment_rating'
    #             ],
    #         'mountain_climbing': [
    #             'global_rating', 'height_diff_difficulties',
    #             'engagment_rating'
    #             ],
    #         'rock_climbing': [
    #             'global_raing', 'equipment_rating',
    #             'rock_free_rating'],
    #         'ice_climbing': ['ice_rating'],
    #         'via_ferrata': ['via_ferrata_rating'],
    #         'hiking': ['mtb_up_rating', 'mtb_down_rating']
    #          }
    for table in update_tables:
        op.add_column(
            table,
            sa.Column('height_diff_difficulties', sa.SmallInteger(),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('ski_rating',
                      sa.Enum(
                          '1.1', '1.2', '1.3', '2.1', '2.2', '2.3', '3.1',
                          '3.2', '3.3', '4.1', '4.2', '4.3', '5.1', '5.2',
                          '5.3', '5.4', '5.5', '5.6', name='ski_rating',
                          schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('labande_global_rating',
                      sa.Enum(
                          'F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+',
                          'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED',
                          'ED+', 'ED4', 'ED5', 'ED6', 'ED7',
                          name='global_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('global_rating',
                      sa.Enum(
                          'F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+',
                          'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED',
                          'ED+', 'ED4', 'ED5', 'ED6', 'ED7',
                          name='global_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('engagement_rating',
                      sa.Enum('I', 'II', 'III', 'IV', 'V', 'VI',
                              name='engagement_rating',
                              schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('equipment_rating',
                      sa.Enum('P1', 'P1+', 'P2', 'P2+', 'P3', 'P3+', 'P4',
                              'P4+', name='equipment_rating',
                              schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('ice_rating',
                      sa.Enum(
                          '1', '2', '3', '3+', '4', '4+', '5', '5+', '6', '6+',
                          '7', '7+',
                          name='ice_rating',
                          schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('rock_free_rating',
                      sa.Enum(
                          '2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+',
                          '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+',
                          '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+',
                          '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+',
                          '9b', '9b+', '9c', '9c+',
                          name='climbing_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('via_ferrata_rating',
                      sa.Enum('K1', 'K2', 'K3', 'K4', 'K5', 'K6',
                              name='via_ferrata_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('hiking_rating',
                      sa.Enum('T1', 'T2', 'T3', 'T4', 'T5',
                              name='hiking_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('snowshoe_rating',
                      sa.Enum('R1', 'R2', 'R3', 'R4', 'R5',
                              name='snowshoe_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('mtb_up_rating',
                      sa.Enum('M1', 'M2', 'M3', 'M4', 'M5',
                              name='mtb_up_rating', schema='guidebook'),
                      nullable=True),
            schema='guidebook')

        op.add_column(
            table,
            sa.Column('mtb_down_rating',
                      sa.Enum('V1', 'V2', 'V3', 'V4', 'V5',
                              name='mtb_down_rating',
                              schema='guidebook'),
                      nullable=True),
            schema='guidebook')

    # update the columns using a sql script
    # this will fill the ratings in the outings table
    # using the best route rating for each activity associated with the outing
    connection = op.get_bind()
    raw_file = join(dirname(__file__), '24f8da659c78_outings.sql')
    f = codecs.open(raw_file, encoding='utf-8')
    content = f.read()
    connection.execute(text(content))

    # we loop over every existing outing
    for document in connection.execute(outings_table.select()):
        document_id = document[0]
        # Add new row to document_archive
        doc_archives_query = """
           INSERT INTO guidebook.documents_archives (
               version, protected, quality,
               type, redirects_to, document_id)
           SELECT
               version +1, protected, quality,
               type, redirects_to, da.document_id
           FROM guidebook.documents_archives da
           WHERE da.document_id = {} ORDER by version DESC LIMIT 1
           RETURNING id
        """.format(document_id)
        doc_archive_id = connection.execute(doc_archives_query).first()[0]

        # outings_archive
        outing_archive_sql = """
        INSERT INTO guidebook.outings_archives (
            activities,
            date_start,
            date_end,
            frequentation,
            participant_count,
            elevation_min,elevation_max,
            elevation_access,
            elevation_up_snow,
            elevation_down_snow,
            height_diff_up,
            height_diff_down,
            length_total,
            partial_trip,
            public_transport,
            access_condition,
            lift_status,
            condition_rating,
            snow_quantity,
            snow_quality,
            glacier_rating,
            avalanche_signs,
            hut_status,
            disable_comments,
            height_diff_difficulties,
            ski_rating,
            labande_global_rating,
            global_rating,
            engagement_rating,
            equipment_rating,
            ice_rating,
            rock_free_rating,
            via_ferrata_rating,
            hiking_rating,
            snowshoe_rating,
            mtb_up_rating,
            mtb_down_rating,
            id)
        SELECT
            activities,
            date_start,
            date_end,
            frequentation,
            participant_count,
            elevation_min,elevation_max,
            elevation_access,
            elevation_up_snow,
            elevation_down_snow,
            height_diff_up,
            height_diff_down,
            length_total,
            partial_trip,
            public_transport,
            access_condition,
            lift_status,
            condition_rating,
            snow_quantity,
            snow_quality,
            glacier_rating,
            avalanche_signs,
            hut_status,
            disable_comments,
            height_diff_difficulties,
            ski_rating,
            labande_global_rating,
            global_rating,
            engagement_rating,
            equipment_rating,
            ice_rating,
            rock_free_rating,
            via_ferrata_rating,
            hiking_rating,
            snowshoe_rating,
            mtb_up_rating,
            mtb_down_rating,
            {}
        FROM guidebook.outings
        WHERE document_id = {}
        """.format(doc_archive_id, document_id)
        op.execute(outing_archive_sql)

        # insert in metadata
        # 2 corresponds to the Camptocamp-Association user
        query_metadata = """INSERT INTO guidebook.history_metadata (user_id, written_at, comment)
                SELECT 2, current_timestamp, '{}'
                RETURNING id
                 """.format(update_text)
        history_metadata_id = connection.execute(query_metadata).first()[0]

        # insert into document_versions
        documents_version_query = """
            INSERT INTO guidebook.documents_versions
            (document_id, lang, document_archive_id,
            document_locales_archive_id, document_geometry_archive_id,
            history_metadata_id)
            SELECT {}, dv.lang, {}, dv.document_locales_archive_id,
            dv.document_geometry_archive_id, {}
            from guidebook.documents_versions dv
            WHERE document_id = {}
            ORDER BY id DESC LIMIT 1""".format(document_id,
                                               doc_archive_id,
                                               history_metadata_id,
                                               document_id)
        op.execute(documents_version_query)

    # update document
    query_documents = """
        UPDATE guidebook.documents
        SET version = version +1 where type = 'o';"""
    op.execute(query_documents)


def downgrade():
    connection = op.get_bind()
    for document in connection.execute(ll.select().where(ll.c.comment == update_text)):
        meta_id = document[0]
        delete_metadata_query = """DELETE FROM guidebook.history_metadata
                            WHERE id = {}""".format(meta_id)
        op.execute(delete_metadata_query)
        delete_documents_versions = """
            DELETE FROM guidebook.documents_versions
            WHERE history_metadata_id = {}
            RETURNING document_archive_id""".format(meta_id)
        doc_archive_id = connection.execute(delete_documents_versions).first()[0]
        delete_documents_archives = """DELETE FROM guidebook.documents_archives
                                WHERE id = {}""".format(doc_archive_id)
        op.execute(delete_documents_archives)

        delete_outings_archives = """DELETE FROM guidebook.outings_archives
                                WHERE id = {}""".format(doc_archive_id)
        op.execute(delete_outings_archives)
        # update document
    query_documents = """
        UPDATE guidebook.documents
        SET version = version -1 where type = 'o';"""
    op.execute(query_documents)

    for table in update_tables:
        op.drop_column(table, 'height_diff_difficulties', schema='guidebook')
        op.drop_column(table, 'ski_rating', schema='guidebook')
        op.drop_column(table, 'labande_global_rating', schema='guidebook')
        op.drop_column(table, 'global_rating', schema='guidebook')
        op.drop_column(table, 'engagement_rating', schema='guidebook')
        op.drop_column(table, 'equipment_rating', schema='guidebook')
        op.drop_column(table, 'ice_rating', schema='guidebook')
        op.drop_column(table, 'rock_free_rating', schema='guidebook')
        op.drop_column(table, 'via_ferrata_rating', schema='guidebook')
        op.drop_column(table, 'hiking_rating', schema='guidebook')
        op.drop_column(table, 'snowshoe_rating', schema='guidebook')
        op.drop_column(table, 'mtb_up_rating', schema='guidebook')
        op.drop_column(table, 'mtb_down_rating', schema='guidebook')
