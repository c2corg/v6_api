from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger,\
    QEnumArray, QEnum
from c2corg_api.search.utils import get_title


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE

    activities = QEnumArray(
        'ac', model_field=Route.activities)
    elevation_min = QInteger(
        'emi', range=True)
    elevation_max = QInteger(
        'ema', range=True)
    height_diff_up = QInteger(
        'hdu', range=True)
    height_diff_down = QInteger(
        'hdd', range=True)
    route_length = QInteger(
        'rl', range=True)
    difficulties_height = QInteger(
        'dh', range=True)
    height_diff_access = QInteger(
        'hda', range=True)
    height_diff_difficulties = QInteger(
        'hddi', range=True)
    route_types = QEnumArray(
         'rt', model_field=Route.route_types)
    orientations = QEnumArray(
         'o', model_field=Route.orientations)
    durations = QEnumArray(
         'd', model_field=Route.durations)
    glacier_gear = QEnum(
         'gg', model_field=Route.glacier_gear)
    configuration = QEnumArray(
         'c', model_field=Route.configuration)
    ski_rating = QEnum(
         'sr', model_field=Route.ski_rating)
    ski_exposition = QEnum(
         'se', model_field=Route.ski_exposition)
    labande_ski_rating = QEnum(
         'lsr', model_field=Route.labande_ski_rating)
    labande_global_rating = QEnum(
         'lgr', model_field=Route.labande_global_rating)
    global_rating = QEnum(
         'gr', model_field=Route.global_rating)
    engagement_rating = QEnum(
         'er', model_field=Route.engagement_rating)
    risk_rating = QEnum(
         'rr', model_field=Route.risk_rating)
    equipment_rating = QEnum(
         'eqr', model_field=Route.equipment_rating)
    ice_rating = QEnum(
         'ir', model_field=Route.ice_rating)
    mixed_rating = QEnum(
         'mr', model_field=Route.mixed_rating)
    exposition_rock_rating = QEnum(
         'err', model_field=Route.exposition_rock_rating)
    rock_free_rating = QEnum(
         'rfr', model_field=Route.rock_free_rating)
    rock_required_rating = QEnum(
         'rrqr', model_field=Route.rock_required_rating)
    aid_rating = QEnum(
         'ar', model_field=Route.aid_rating)
    via_ferrata_rating = QEnum(
         'vfr', model_field=Route.via_ferrata_rating)
    hiking_rating = QEnum(
         'hr', model_field=Route.hiking_rating)
    hiking_mtb_exposition = QEnum(
         'e', model_field=Route.hiking_mtb_exposition)
    snowshoe_rating = QEnum(
         'ssr', model_field=Route.snowshoe_rating)
    mtb_up_rating = QEnum(
         'mur', model_field=Route.mtb_up_rating)
    mtb_down_rating = QEnum(
         'mdr', model_field=Route.mtb_down_rating)
    mtb_length_asphalt = QInteger(
        'mla', range=True)
    mtb_length_trail = QInteger(
        'mlt', range=True)
    mtb_height_diff_portages = QInteger(
        'mdp', range=True)
    rock_types = QEnumArray(
         'rct', model_field=Route.rock_types)
    climbing_outdoor_type = QEnumArray(
         'cot', model_field=Route.climbing_outdoor_type)

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
