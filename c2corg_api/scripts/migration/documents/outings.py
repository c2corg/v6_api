from c2corg_api.models.outing import OutingLocale, Outing, ArchiveOuting, \
    ArchiveOutingLocale, OUTING_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes


class MigrateOutings(MigrateDocuments):

    def get_name(self):
        return 'outings'

    def get_model_document(self, locales):
        return OutingLocale if locales else Outing

    def get_model_archive_document(self, locales):
        return ArchiveOutingLocale if locales else ArchiveOuting

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) from app_outings_archives;'
        )

    def get_query(self):
        return (
            'select '
            '   id, document_archive_id, is_latest_version, elevation, '
            '   is_protected, redirects_to, '
            '   ST_Force2D(ST_SetSRID(geom, 3857)) geom, '
            '   date, activities, height_diff_up, height_diff_down, '
            '   outing_length, min_elevation, max_elevation, partial_trip, '
            '   hut_status, frequentation_status, conditions_status, '
            '   access_status, access_elevation, lift_status, glacier_status, '
            '   up_snow_elevation, down_snow_elevation, track_status, '
            '   outing_with_public_transportation, avalanche_date '
            'from app_outings_archives '
            'order by id, document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_outings_i18n_archives;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   id, document_i18n_archive_id, is_latest_version, culture, '
            '   name, description, participants, timing, weather, '
            '   hut_comments, access_comments, conditions, conditions_levels, '
            '   avalanche_desc, outing_route_desc '
            'from app_outings_i18n_archives '
            ' order by id, document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        activities = self.convert_types(
            document_in.activities, MigrateRoutes.activities)
        if activities is None:
            # there are ~100 outings which do not have an activity. because
            # only one of them is the latest version, we assign a default
            # activity (in v6 activities are required)
            activities = ['skitouring']

        return dict(
            document_id=document_in.id,
            type=OUTING_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            activities=activities,
            access_condition=self.convert_type(
                document_in.access_status,
                MigrateOutings.access_conditions),
            avalanche_signs=self.convert_types(
                document_in.avalanche_date,
                MigrateOutings.avalanche_signs),
            condition_rating=self.convert_type(
                document_in.conditions_status,
                MigrateOutings.condition_ratings),
            date_end=document_in.date,
            date_start=document_in.date,
            elevation_access=document_in.access_elevation,
            elevation_down_snow=document_in.down_snow_elevation,
            elevation_up_snow=document_in.up_snow_elevation,
            elevation_max=document_in.max_elevation,
            elevation_min=document_in.min_elevation,
            frequentation=self.convert_type(
                document_in.frequentation_status,
                MigrateOutings.frequentation_types),
            glacier_rating=self.convert_type(
                document_in.glacier_status,
                MigrateOutings.glacier_ratings),
            height_diff_down=document_in.height_diff_down,
            height_diff_up=document_in.height_diff_up,
            hut_status=self.convert_type(
                document_in.hut_status,
                MigrateOutings.hut_status),
            length_total=document_in.outing_length,
            lift_status=self.convert_type(
                document_in.lift_status,
                MigrateOutings.lift_status),
            partial_trip=document_in.partial_trip,
            public_transport=document_in.outing_with_public_transportation
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=OUTING_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,
            access_comment=document_in.access_comments,
            avalanches=document_in.avalanche_desc,
            route_description=document_in.outing_route_desc,
            conditions=document_in.conditions,
            conditions_levels=document_in.conditions_levels,
            hut_comment=document_in.hut_comments,
            participants=document_in.participants,
            timing=document_in.timing,
            weather=document_in.weather
        )

    access_conditions = {
        '2': 'cleared',
        '4': 'snow',
        '6': 'closed_snow'
    }

    avalanche_signs = {
        '1': 'no',
        '2': 'danger_sign',
        '3': 'recent_avalanche',
        '4': 'natural_avalanche',
        '5': 'accidental_avalanche'
    }

    condition_ratings = {
        '1': 'excellent',
        '2': 'good',
        '3': 'average',
        '4': 'poor',
        '5': 'awful'
    }

    frequentation_types = {
        '1': None,
        '2': 'quiet',
        '4': 'some',
        '6': 'crowded',
        '8': 'overcrowded'
    }

    glacier_ratings = {
        '2': 'easy',
        '4': 'possible',
        '6': 'difficult',
        '8': 'impossible'
    }

    hut_status = {
        '2': 'open_guarded',
        '4': 'open_non_guarded',
        '6': 'closed',
        '8': None
    }

    lift_status = {
        '2': 'open',
        '4': 'closed'
    }
