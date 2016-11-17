from c2corg_api.models.outing import OutingLocale, Outing, ArchiveOuting, \
    ArchiveOutingLocale, OUTING_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes
import phpserialize
import json

from c2corg_api.scripts.migration.migrate_base import parse_php_object


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
            geom_detail=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_outings_archives oa join outings o on oa.id = o.id '
            'where o.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   oa.id, oa.document_archive_id, oa.is_latest_version, '
            '   oa.elevation, oa.is_protected, oa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(oa.geom, 3857)) geom, '
            '   oa.date, oa.activities, oa.height_diff_up, '
            '   oa.height_diff_down, oa.outing_length, oa.min_elevation, '
            '   oa.max_elevation, oa.partial_trip, '
            '   oa.hut_status, oa.frequentation_status, oa.conditions_status, '
            '   oa.access_status, oa.access_elevation, oa.lift_status, '
            '   oa.glacier_status, oa.up_snow_elevation, '
            '   oa.down_snow_elevation, oa.track_status, '
            '   oa.outing_with_public_transportation, oa.avalanche_date '
            'from app_outings_archives oa join outings o on oa.id = o.id '
            'where o.redirects_to is null '
            'order by oa.id, oa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_outings_i18n_archives oa join outings o on oa.id = o.id '
            'where o.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   oa.id, oa.document_i18n_archive_id, oa.is_latest_version, '
            '   oa.culture, oa.name, oa.description, oa.participants, '
            '   oa.timing, oa.weather, oa.hut_comments, oa.access_comments, '
            '   oa.conditions, oa.conditions_levels, oa.avalanche_desc, '
            '   oa.outing_route_desc '
            'from app_outings_i18n_archives oa join outings o on oa.id = o.id '
            'where o.redirects_to is null '
            'order by oa.id, oa.culture, oa.document_i18n_archive_id;'
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
            public_transport=document_in.outing_with_public_transportation,
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=OUTING_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,
            access_comment=self.convert_tags(document_in.access_comments),
            avalanches=self.convert_tags(document_in.avalanche_desc),
            route_description=self.convert_tags(document_in.outing_route_desc),
            conditions=self.convert_tags(document_in.conditions),
            conditions_levels=php_to_json(
                document_in.conditions_levels,
                document_in.document_i18n_archive_id),
            hut_comment=self.convert_tags(document_in.hut_comments),
            participants=self.convert_tags(document_in.participants),
            timing=self.convert_tags(document_in.timing),
            weather=self.convert_tags(document_in.weather)
        )

    access_conditions = {
        '2': 'cleared',
        '4': 'snowy',
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
        '6': 'closed_hut',
        '8': None
    }

    lift_status = {
        '2': 'open',
        '4': 'closed'
    }


def php_to_json(conditions_levels_serialized, id):
    """Convert the condition levels which were stored as serialized PHP
    objects to a JSON string.
    """
    if not conditions_levels_serialized:
        return None

    try:
        levels = parse_php_object(conditions_levels_serialized)
        return json.dumps(phpserialize.dict_to_list(levels))
    except Exception as e:
        print(id)
        raise e
