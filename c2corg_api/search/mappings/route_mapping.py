from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta, Enum, EnumArray
from elasticsearch_dsl import Integer
from c2corg_api.search.utils import get_title


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE

    activities = EnumArray()
    elevation_min = Integer()
    elevation_max = Integer()
    height_diff_up = Integer()
    height_diff_down = Integer()
    route_length = Integer()
    difficulties_height = Integer()
    height_diff_access = Integer()
    height_diff_difficulties = Integer()
    route_types = EnumArray()
    orientations = EnumArray()
    durations = EnumArray()
    glacier_gear = Enum()
    configuration = EnumArray()
    ski_rating = Enum()
    ski_exposition = Enum()
    labande_ski_rating = Enum()
    labande_global_rating = Enum()
    global_rating = Enum()
    engagement_rating = Enum()
    risk_rating = Enum()
    equipment_rating = Enum()
    ice_rating = Enum()
    mixed_rating = Enum()
    exposition_rock_rating = Enum()
    rock_free_rating = Enum()
    rock_required_rating = Enum()
    aid_rating = Enum()
    via_ferrata_rating = Enum()
    hiking_rating = Enum()
    hiking_mtb_exposition = Enum()
    snowshoe_rating = Enum()
    mtb_up_rating = Enum()
    mtb_down_rating = Enum()
    mtb_length_asphalt = Integer()
    mtb_length_trail = Integer()
    mtb_height_diff_portages = Integer()
    rock_types = EnumArray()
    climbing_outdoor_type = EnumArray()

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
