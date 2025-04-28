from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger, \
    QEnumArray, QEnum, QLong, QEnumRange, QNumberRange
from c2corg_api.search.utils import get_title
from c2corg_api.models.common.sortable_search_attributes import \
    sortable_route_duration_types, sortable_ski_ratings, \
    sortable_exposition_ratings, sortable_labande_ski_ratings, \
    sortable_global_ratings, sortable_engagement_ratings, \
    sortable_risk_ratings, sortable_equipment_ratings, sortable_ice_ratings, \
    sortable_mixed_ratings, sortable_exposition_rock_ratings, \
    sortable_aid_ratings, sortable_via_ferrata_ratings, \
    sortable_hiking_ratings, sortable_snowshoe_ratings, \
    sortable_mtb_up_ratings, sortable_mtb_down_ratings, \
    sortable_climbing_ratings


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE

    # array of waypoint ids
    waypoints = QLong('w', is_id=True)

    # array of user ids
    users = QLong('u', is_id=True)

    activities = QEnumArray(
        'act', model_field=Route.activities)
    elevation_min = QInteger(
        'rmina', range=True)
    elevation_max = QInteger(
        'rmaxa', range=True)
    height_diff_up = QInteger(
        'hdif', range=True)
    height_diff_down = QInteger(
        'ddif', range=True)
    route_length = QInteger(
        'rlen', range=True)
    difficulties_height = QInteger(
        'ralt', range=True)
    height_diff_access = QInteger(
        'rappr', range=True)
    height_diff_difficulties = QInteger(
        'dhei', range=True)
    route_types = QEnumArray(
        'rtyp', model_field=Route.route_types)
    orientations = QEnumArray(
        'fac', model_field=Route.orientations)
    durations = QEnumRange(
        'time', model_field=Route.durations,
        enum_mapper=sortable_route_duration_types)
    glacier_gear = QEnum(
        'glac', model_field=Route.glacier_gear)
    configuration = QEnumArray(
        'conf', model_field=Route.configuration)
    ski_rating = QEnumRange(
        'trat', model_field=Route.ski_rating,
        enum_mapper=sortable_ski_ratings)
    ski_exposition = QEnumRange(
        'sexpo', model_field=Route.ski_exposition,
        enum_mapper=sortable_exposition_ratings)
    labande_ski_rating = QEnumRange(
        'srat', model_field=Route.labande_ski_rating,
        enum_mapper=sortable_labande_ski_ratings)
    labande_global_rating = QEnumRange(
        'lrat', model_field=Route.labande_global_rating,
        enum_mapper=sortable_global_ratings)
    global_rating = QEnumRange(
        'grat', model_field=Route.global_rating,
        enum_mapper=sortable_global_ratings)
    engagement_rating = QEnumRange(
        'erat', model_field=Route.engagement_rating,
        enum_mapper=sortable_engagement_ratings)
    risk_rating = QEnumRange(
        'orrat', model_field=Route.risk_rating,
        enum_mapper=sortable_risk_ratings)
    equipment_rating = QEnumRange(
        'prat', model_field=Route.equipment_rating,
        enum_mapper=sortable_equipment_ratings)
    ice_rating = QEnumRange(
        'irat', model_field=Route.ice_rating,
        enum_mapper=sortable_ice_ratings)
    mixed_rating = QEnumRange(
        'mrat', model_field=Route.mixed_rating,
        enum_mapper=sortable_mixed_ratings)
    exposition_rock_rating = QEnumRange(
        'rexpo', model_field=Route.exposition_rock_rating,
        enum_mapper=sortable_exposition_rock_ratings)
    rock_free_rating = QEnumRange(
        'frat', model_field=Route.rock_free_rating,
        enum_mapper=sortable_climbing_ratings)
    bouldering_rating = QEnumRange(
        'frat', model_field=Route.bouldering_rating,
        enum_mapper=sortable_climbing_ratings)
    rock_required_rating = QEnumRange(
        'rrat', model_field=Route.rock_required_rating,
        enum_mapper=sortable_climbing_ratings)
    aid_rating = QEnumRange(
        'arat', model_field=Route.aid_rating,
        enum_mapper=sortable_aid_ratings)
    via_ferrata_rating = QEnumRange(
        'krat', model_field=Route.via_ferrata_rating,
        enum_mapper=sortable_via_ferrata_ratings)
    hiking_rating = QEnumRange(
        'hrat', model_field=Route.hiking_rating,
        enum_mapper=sortable_hiking_ratings)
    hiking_mtb_exposition = QEnumRange(
        'hexpo', model_field=Route.hiking_mtb_exposition,
        enum_mapper=sortable_exposition_ratings)
    snowshoe_rating = QEnumRange(
        'wrat', model_field=Route.snowshoe_rating,
        enum_mapper=sortable_snowshoe_ratings)
    mtb_up_rating = QEnumRange(
        'mbur', model_field=Route.mtb_up_rating,
        enum_mapper=sortable_mtb_up_ratings)
    mtb_down_rating = QEnumRange(
        'mbdr', model_field=Route.mtb_down_rating,
        enum_mapper=sortable_mtb_down_ratings)
    mtb_length_asphalt = QInteger(
        'mbroad', range=True)
    mtb_length_trail = QInteger(
        'mbtrack', range=True)
    mtb_height_diff_portages = QInteger(
        'mbpush', range=True)
    rock_types = QEnumArray(
        'rock', model_field=Route.rock_types)
    climbing_outdoor_type = QEnumArray(
        'crtyp', model_field=Route.climbing_outdoor_type)
    slackline_type = QEnum(
        'sltyp', model_field=Route.slackline_type)

    FIELDS = [
        'activities', 'elevation_min', 'elevation_max', 'height_diff_up',
        'height_diff_down', 'route_length', 'difficulties_height',
        'height_diff_access', 'height_diff_difficulties', 'route_types',
        'orientations', 'glacier_gear', 'configuration',
        'mtb_length_asphalt', 'mtb_length_trail',
        'mtb_height_diff_portages', 'rock_types', 'climbing_outdoor_type',
        'slackline_type'
    ]

    ENUM_RANGE_FIELDS = [
        'durations', 'ski_rating', 'ski_exposition', 'labande_ski_rating',
        'labande_global_rating', 'global_rating', 'engagement_rating',
        'risk_rating', 'equipment_rating', 'ice_rating', 'mixed_rating',
        'exposition_rock_rating', 'rock_free_rating', 'rock_required_rating',
        'aid_rating', 'via_ferrata_rating', 'hiking_rating',
        'hiking_mtb_exposition', 'snowshoe_rating', 'mtb_up_rating',
        'mtb_down_rating',
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchRoute.FIELDS)

        SearchDocument.copy_enum_range_fields(
            search_document, document, SearchRoute.ENUM_RANGE_FIELDS,
            SearchRoute)

        for locale in document.locales:
            search_document['title_' + locale.lang] = \
                get_title(locale.title, locale.title_prefix)

        if document.associated_waypoints_ids:
            # add the document ids of associated waypoints and of the parent
            # and grand-parents of these waypoints
            search_document['waypoints'] = \
                document.associated_waypoints_ids.waypoint_ids

        if document.associated_users_ids:
            # add the document ids of associated users
            search_document['users'] = \
                document.associated_users_ids.user_ids

        return search_document


SearchRoute.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchRoute)
SearchRoute.queryable_fields['ele'] = QNumberRange(
    'elevation', 'elevation_min', 'elevation_max')
