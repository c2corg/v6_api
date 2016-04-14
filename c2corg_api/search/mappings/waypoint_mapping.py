from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta, Enum, EnumArray
from elasticsearch_dsl import Integer, Boolean


class SearchWaypoint(SearchDocument):
    class Meta(BaseMeta):
        doc_type = WAYPOINT_TYPE

    elevation = Integer()
    waypoint_type = Enum()
    rock_types = EnumArray()
    orientations = EnumArray()
    best_periods = EnumArray()
    has_phone = Boolean()
    lift_access = Boolean()
    custodianship = Enum()
    climbing_styles = EnumArray()
    access_time = Enum()
    climbing_rating_max = Enum()
    climbing_rating_min = Enum()
    climbing_rating_median = Enum()
    height_max = Integer()
    height_min = Integer()
    height_median = Integer()
    routes_quantity = Integer()
    children_proof = Enum()
    rain_proof = Enum()
    paragliding_rating = Enum()
    exposition_rating = Enum()
    length = Integer()
    weather_station_types = EnumArray()
    capacity = Integer()
    capacity_staffed = Integer()
    climbing_styles = EnumArray()
    equipment_ratings = EnumArray()
    public_transportation_types = EnumArray()
    public_transportation_rating = Enum()
    snow_clearance_rating = Enum()
    product_types = EnumArray()

    FIELDS = [
        'elevation', 'waypoint_type', 'rock_types', 'orientations',
        'best_periods', 'lift_access', 'custodianship', 'climbing_styles',
        'access_time', 'climbing_rating_max', 'climbing_rating_min',
        'climbing_rating_median', 'height_max', 'height_min', 'height_median',
        'routes_quantity', 'children_proof', 'rain_proof',
        'paragliding_rating', 'exposition_rating', 'length',
        'weather_station_types', 'capacity', 'capacity_staffed',
        'climbing_styles', 'equipment_ratings', 'public_transportation_types',
        'public_transportation_rating', 'snow_clearance_rating',
        'product_types'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchWaypoint.FIELDS)
        search_document['has_phone'] = not (not (
            document.phone or document.phone_custodian))

        return search_document
