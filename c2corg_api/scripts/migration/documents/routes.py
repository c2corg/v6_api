from c2corg_api.models.route import Route, RouteLocale, ArchiveRoute, \
    ArchiveRouteLocale, ROUTE_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY


class MigrateRoutes(MigrateDocuments):

    def get_name(self):
        return 'routes'

    def get_model_document(self, locales):
        return RouteLocale if locales else Route

    def get_model_archive_document(self, locales):
        return ArchiveRouteLocale if locales else ArchiveRoute

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
            'from app_routes_archives ra join routes r on ra.id = r.id '
            'where r.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   ra.id, ra.document_archive_id, ra.is_latest_version, '
            '   ra.elevation, ra.is_protected, ra.redirects_to, '
            '   ST_Simplify(ST_SetSRID(ra.geom, 3857), 5) geom, '
            '   ra.activities, ra.facing, ra.height_diff_up, '
            '   ra.height_diff_down, ra.route_type, ra.route_length, '
            '   ra.min_elevation, ra.max_elevation, ra.duration, ra.slope, '
            '   ra.difficulties_height, ra.configuration, '
            '   ra.global_rating, ra.engagement_rating, ra.equipment_rating, '
            '   ra.is_on_glacier, ra.sub_activities, '
            '   ra.toponeige_technical_rating, '
            '   ra.toponeige_exposition_rating, ra.labande_ski_rating, '
            '   ra.labande_global_rating, ra.ice_rating, ra.mixed_rating, '
            '   ra.rock_free_rating, ra.bouldering_rating, ra.rock_required_rating, ra.aid_rating, '
            '   ra.hiking_rating, ra.snowshoeing_rating, '
            '   ra.objective_risk_rating, ra.rock_exposition_rating '
            'from app_routes_archives ra join routes r on ra.id = r.id '
            'where r.redirects_to is null '
            'order by ra.id, ra.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_routes_i18n_archives ra join routes r on ra.id = r.id '
            'where r.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   ra.id, ra.document_i18n_archive_id, ra.is_latest_version, '
            '   ra.culture, ra.name, ra.description, ra.remarks, ra.gear, '
            '   ra.route_history, ra.external_resources, r.slope '
            'from app_routes_i18n_archives ra join routes r on ra.id = r.id '
            'where r.redirects_to is null '
            'order by ra.id, ra.culture, ra.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        activities = self.convert_types(
            document_in.activities, MigrateRoutes.activities)
        if activities is None:
            # there are 63 routes which do not have an activity. because all
            # of them are not the latest version, we assign a default activity
            # (in v6 activities are required)
            activities = ['skitouring']

        climbing_outdoor_type = None
        if 'rock_climbing' in activities and 'hiking' not in activities:
            climbing_outdoor_type = 'multi'

        orientations = self.convert_type(
            document_in.facing, MigrateRoutes.orientation_types)
        if orientations is not None:
            orientations = [orientations]

        route_types = self.convert_type(
            document_in.route_type, MigrateRoutes.route_types)
        if route_types is not None:
            route_types = [route_types]

        durations = self.convert_type(
            document_in.duration, MigrateRoutes.duration_types)
        if durations is not None:
            durations = [durations]

        glacier_gear = 'no'
        if document_in.is_on_glacier:
            glacier_gear = 'glacier_safety_gear'

        lift_access = None
        if document_in.sub_activities is not None:
            if 8 in document_in.sub_activities:
                lift_access = True

        return dict(
            document_id=document_in.id,
            type=ROUTE_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            # elevation=document_in.elevation,  # used for difficulties_height
            activities=activities,
            climbing_outdoor_type=climbing_outdoor_type,
            orientations=orientations,
            height_diff_up=document_in.height_diff_up,
            height_diff_down=document_in.height_diff_down,
            route_types=route_types,
            route_length=document_in.route_length,
            elevation_min=document_in.min_elevation,
            elevation_max=document_in.max_elevation,
            durations=durations,
            difficulties_height=document_in.elevation,  # !
            height_diff_difficulties=document_in.difficulties_height,
            configuration=self.convert_types(
                document_in.configuration,
                MigrateRoutes.route_configuration_types),
            global_rating=self.convert_type(
                document_in.global_rating,
                MigrateRoutes.global_ratings),
            engagement_rating=self.convert_type(
                document_in.engagement_rating,
                MigrateRoutes.engagement_ratings),
            equipment_rating=self.convert_type(
                document_in.equipment_rating,
                MigrateRoutes.equipment_ratings),
            glacier_gear=glacier_gear,
            lift_access=lift_access,
            ski_rating=self.convert_type(
                document_in.toponeige_technical_rating,
                MigrateRoutes.ski_ratings),
            ski_exposition=self.convert_type(
                document_in.toponeige_exposition_rating,
                MigrateRoutes.exposition_ratings),
            labande_ski_rating=self.convert_type(
                document_in.labande_ski_rating,
                MigrateRoutes.labande_ski_ratings),
            labande_global_rating=self.convert_type(
                document_in.labande_global_rating,
                MigrateRoutes.global_ratings),
            ice_rating=self.convert_type(
                document_in.ice_rating,
                MigrateRoutes.ice_ratings),
            mixed_rating=self.convert_type(
                document_in.mixed_rating,
                MigrateRoutes.mixed_ratings),
            rock_free_rating=self.convert_type(
                document_in.rock_free_rating,
                MigrateRoutes.climbing_rating),
            bouldering_rating=self.convert_type(
                document_in.bouldering_rating,
                MigrateRoutes.climbing_rating),
            rock_required_rating=self.convert_type(
                document_in.rock_required_rating,
                MigrateRoutes.climbing_rating),
            aid_rating=self.convert_type(
                document_in.aid_rating,
                MigrateRoutes.aid_ratings),
            hiking_rating=self.convert_type(
                document_in.hiking_rating,
                MigrateRoutes.hiking_ratings),
            snowshoe_rating=self.convert_type(
                document_in.snowshoeing_rating,
                MigrateRoutes.snowshoe_ratings),
            risk_rating=self.convert_type(
                document_in.objective_risk_rating,
                MigrateRoutes.risk_ratings),
            exposition_rock_rating=self.convert_type(
                document_in.rock_exposition_rating,
                MigrateRoutes.exposition_rock_ratings),
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=ROUTE_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,
            remarks=self.convert_tags(document_in.remarks),
            gear=self.convert_tags(document_in.gear),
            route_history=self.convert_tags(document_in.route_history),
            external_resources=self.convert_tags(
                document_in.external_resources),
            slope=document_in.slope
        )

    activities = {
        '1': 'skitouring',
        '2': 'snow_ice_mixed',
        '3': 'mountain_climbing',
        '4': 'rock_climbing',
        '5': 'ice_climbing',
        '6': 'hiking',
        '7': 'snowshoeing',
        '8': 'paragliding'
    }

    # orientation types for routes (not the same codes for sites!)
    orientation_types = {
        '1': 'N',
        '8': 'NE',
        '7': 'E',
        '6': 'SE',
        '5': 'S',
        '4': 'SW',
        '3': 'W',
        '2': 'NW'
    }

    route_types = {
        '1': 'return_same_way',
        '2': 'loop',
        '3': 'traverse'
    }

    duration_types = {
        '1': '1',   # 1/2 becomes 1
        '2': '1',
        '4': '2',
        '6': '3',
        '8': '4',
        '10': '5',
        '12': '6',
        '14': '7',
        '16': '8',
        '18': '9',
        '20': '10',
        '22': '10+'
    }

    route_configuration_types = {
        '1': 'edge',
        '5': 'pillar',
        '3': 'face',
        '2': 'corridor',
        '4': 'goulotte',
        '6': None,  # invalid type, ignore
        '7': 'glacier'
    }

    global_ratings = {
        '2': 'F',
        '3': 'F+',
        '4': 'PD-',
        '6': 'PD',
        '8': 'PD+',
        '10': 'AD-',
        '12': 'AD',
        '14': 'AD+',
        '16': 'D-',
        '18': 'D',
        '20': 'D+',
        '22': 'TD-',
        '24': 'TD',
        '26': 'TD+',
        '28': 'ED-',
        '30': 'ED',
        '32': 'ED+',
        '34': 'ED4',
        '36': 'ED5',
        '38': 'ED6',
        '40': 'ED7'
    }

    engagement_ratings = {
        '1': 'I',
        '2': 'II',
        '3': 'III',
        '4': 'IV',
        '5': 'V',
        '6': 'VI'
    }

    equipment_ratings = {
        '4': 'P1',
        '6': 'P1+',
        '8': 'P2',
        '10': 'P2+',
        '12': 'P3',
        '14': 'P3+',
        '16': 'P4',
        '18': 'P4+',
    }

    ski_ratings = {
        '1': '1.1',
        '2': '1.2',
        '3': '1.3',
        '4': '2.1',
        '5': '2.2',
        '6': '2.3',
        '7': '3.1',
        '8': '3.2',
        '9': '3.3',
        '10': '4.1',
        '11': '4.2',
        '12': '4.3',
        '13': '5.1',
        '14': '5.2',
        '15': '5.3',
        '16': '5.4',
        '17': '5.5',
        '18': '5.6'
    }

    exposition_ratings = {
        '1': 'E1',
        '2': 'E2',
        '3': 'E3',
        '4': 'E4'
    }

    labande_ski_ratings = {
        '1': 'S1',
        '2': 'S2',
        '3': 'S3',
        '4': 'S4',
        '5': 'S5',
        '6': 'S6',
        '7': 'S7'
    }

    ice_ratings = {
        '2': '1',
        '4': '2',
        '6': '3',
        '8': '3+',
        '10': '4',
        '12': '4+',
        '14': '5',
        '16': '5+',
        '18': '6',
        '20': '6+',
        '22': '7',
        '24': '7+',
    }

    mixed_ratings = {
        '2': 'M1',
        '4': 'M2',
        '6': 'M3',
        '8': 'M3+',
        '10': 'M4',
        '12': 'M4+',
        '14': 'M5',
        '16': 'M5+',
        '18': 'M6',
        '20': 'M6+',
        '22': 'M7',
        '24': 'M7+',
        '26': 'M8',
        '28': 'M8+',
        '30': 'M9',
        '32': 'M9+',
        '34': 'M10',
        '36': 'M10+',
        '38': 'M11',
        '40': 'M11+',
        '42': 'M12',
        '44': 'M12+',
    }

    climbing_rating = {
        '2': '2',
        '3': '3a',
        '4': '3b',
        '6': '3c',
        '8': '4a',
        '10': '4b',
        '12': '4c',
        '14': '5a',
        '15': '5a+',
        '16': '5b',
        '17': '5b+',
        '18': '5c',
        '19': '5c+',
        '20': '6a',
        '22': '6a+',
        '24': '6b',
        '26': '6b+',
        '28': '6c',
        '30': '6c+',
        '32': '7a',
        '34': '7a+',
        '36': '7b',
        '38': '7b+',
        '40': '7c',
        '42': '7c+',
        '44': '8a',
        '46': '8a+',
        '48': '8b',
        '50': '8b+',
        '52': '8c',
        '54': '8c+',
        '56': '9a',
        '58': '9a+',
        '60': '9b',
        '62': '9b+',
    }

    aid_ratings = {
        '2': 'A0',
        '3': 'A0+',
        '4': 'A1',
        '6': 'A1+',
        '8': 'A2',
        '10': 'A2+',
        '12': 'A3',
        '14': 'A3+',
        '16': 'A4',
        '18': 'A4+',
        '20': 'A5',
        '22': 'A5+',
    }

    hiking_ratings = {
        '1': 'T1',
        '2': 'T2',
        '3': 'T3',
        '4': 'T4',
        '5': 'T5',
        '6': 'T5'  # 6 does not exist anymore
    }

    snowshoe_ratings = {
        '1': 'R1',
        '2': 'R2',
        '3': 'R3',
        '4': 'R4',
        '5': 'R5',
    }

    risk_ratings = {
        '2': 'X1',
        '4': 'X2',
        '6': 'X3',
        '8': 'X4',
        '10': 'X5',
    }

    exposition_rock_ratings = {
        '1': 'E1',
        '2': 'E2',
        '3': 'E3',
        '4': 'E4',
        '5': 'E5',
        '6': 'E6',
    }
