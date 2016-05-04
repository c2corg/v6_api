from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger,\
    QEnumArray, QEnum
from c2corg_api.search.utils import get_title


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE

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
        'ralt ', range=True)
    height_diff_access = QInteger(
        'rappr', range=True)
    height_diff_difficulties = QInteger(
        'dhei ', range=True)
    route_types = QEnumArray(
         'rtyp', model_field=Route.route_types)
    orientations = QEnumArray(
         'fac', model_field=Route.orientations)
    durations = QEnumArray(
         'time', model_field=Route.durations)
    glacier_gear = QEnum(
         'glac', model_field=Route.glacier_gear)
    configuration = QEnumArray(
         'conf', model_field=Route.configuration)
    ski_rating = QEnum(
         'trat', model_field=Route.ski_rating)
    ski_exposition = QEnum(
         'sexpo', model_field=Route.ski_exposition)
    labande_ski_rating = QEnum(
         'srat', model_field=Route.labande_ski_rating)
    labande_global_rating = QEnum(
         'lrat', model_field=Route.labande_global_rating)
    global_rating = QEnum(
         'grat', model_field=Route.global_rating)
    engagement_rating = QEnum(
         'erat', model_field=Route.engagement_rating)
    risk_rating = QEnum(
         'orrat', model_field=Route.risk_rating)
    equipment_rating = QEnum(
         'prat', model_field=Route.equipment_rating)
    ice_rating = QEnum(
         'irat', model_field=Route.ice_rating)
    mixed_rating = QEnum(
         'mrat', model_field=Route.mixed_rating)
    exposition_rock_rating = QEnum(
         'rexpo', model_field=Route.exposition_rock_rating)
    rock_free_rating = QEnum(
         'frat', model_field=Route.rock_free_rating)
    rock_required_rating = QEnum(
         'rrat', model_field=Route.rock_required_rating)
    aid_rating = QEnum(
         'arat', model_field=Route.aid_rating)
    via_ferrata_rating = QEnum(
         'krat', model_field=Route.via_ferrata_rating)
    hiking_rating = QEnum(
         'hrat', model_field=Route.hiking_rating)
    hiking_mtb_exposition = QEnum(
         'hexpo', model_field=Route.hiking_mtb_exposition)
    snowshoe_rating = QEnum(
         'wrat', model_field=Route.snowshoe_rating)
    mtb_up_rating = QEnum(
         'mbur', model_field=Route.mtb_up_rating)
    mtb_down_rating = QEnum(
         'mbdr', model_field=Route.mtb_down_rating)
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

    FIELDS = [
        'activities', 'elevation_min', 'elevation_max', 'height_diff_up',
        'height_diff_down', 'route_length', 'difficulties_height',
        'height_diff_access', 'height_diff_difficulties', 'route_types',
        'orientations', 'durations', 'glacier_gear', 'configuration',
        'ski_rating', 'ski_exposition', 'labande_ski_rating',
        'labande_global_rating', 'global_rating', 'engagement_rating',
        'risk_rating', 'equipment_rating', 'ice_rating', 'mixed_rating',
        'exposition_rock_rating', 'rock_free_rating', 'rock_required_rating',
        'aid_rating', 'via_ferrata_rating', 'hiking_rating',
        'hiking_mtb_exposition', 'snowshoe_rating', 'mtb_up_rating',
        'mtb_down_rating', 'mtb_length_asphalt', 'mtb_length_trail',
        'mtb_height_diff_portages', 'rock_types', 'climbing_outdoor_type'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchRoute.FIELDS)

        for locale in document.locales:
            search_document['title_' + locale.lang] = \
                get_title(locale.title, locale.title_prefix)

        return search_document

SearchRoute.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchRoute)
