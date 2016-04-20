from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger,\
    QEnumArray, QEnum, QBoolean


class SearchWaypoint(SearchDocument):
    class Meta(BaseMeta):
        doc_type = WAYPOINT_TYPE

    elevation = QInteger(
        'we', range=True)
    waypoint_type = QEnum(
        'wt', model_field=Waypoint.waypoint_type)
    rock_types = QEnumArray(
        'wrt', model_field=Waypoint.rock_types)
    orientations = QEnumArray(
        'wo', model_field=Waypoint.orientations)
    best_periods = QEnumArray(
        'wbp', model_field=Waypoint.best_periods)
    has_phone = QBoolean(
        'wp', is_bool=True)
    lift_access = QBoolean(
        'wla', is_bool=True)
    custodianship = QEnum(
        'wc', model_field=Waypoint.custodianship)
    climbing_styles = QEnumArray(
        'wcs', model_field=Waypoint.climbing_styles)
    access_time = QEnum(
        'wat', model_field=Waypoint.access_time)
    climbing_rating_max = QEnum(
        'wrma', model_field=Waypoint.climbing_rating_max)
    climbing_rating_min = QEnum(
        'wrmi', model_field=Waypoint.climbing_rating_min)
    climbing_rating_median = QEnum(
        'wrme', model_field=Waypoint.climbing_rating_median)
    height_max = QInteger(
        'whma', range=True)
    height_min = QInteger(
        'whmi', range=True)
    height_median = QInteger(
        'whme', range=True)
    routes_quantity = QInteger(
        'wrq', range=True)
    children_proof = QEnum(
        'wcp', model_field=Waypoint.children_proof)
    rain_proof = QEnum(
        'wrp', model_field=Waypoint.rain_proof)
    paragliding_rating = QEnum(
        'wpr', model_field=Waypoint.paragliding_rating)
    exposition_rating = QEnum(
        'wer', model_field=Waypoint.exposition_rating)
    length = QInteger(
        'wl', range=True)
    weather_station_types = QEnumArray(
        'wwst', model_field=Waypoint.weather_station_types)
    capacity = QInteger(
        'wca', range=True)
    capacity_staffed = QInteger(
        'wcas', range=True)
    equipment_ratings = QEnumArray(
        'weqr', model_field=Waypoint.equipment_ratings)
    public_transportation_types = QEnumArray(
        'wptt', model_field=Waypoint.public_transportation_types)
    public_transportation_rating = QEnum(
        'wptr', model_field=Waypoint.public_transportation_rating)
    snow_clearance_rating = QEnum(
        'wscr', model_field=Waypoint.snow_clearance_rating)
    product_types = QEnumArray(
        'wpt', model_field=Waypoint.product_types)

    FIELDS = [
        'elevation', 'waypoint_type', 'rock_types', 'orientations',
        'best_periods', 'lift_access', 'custodianship', 'climbing_styles',
        'access_time', 'climbing_rating_max', 'climbing_rating_min',
        'climbing_rating_median', 'height_max', 'height_min', 'height_median',
        'routes_quantity', 'children_proof', 'rain_proof',
        'paragliding_rating', 'exposition_rating', 'length',
        'weather_station_types', 'capacity', 'capacity_staffed',
        'equipment_ratings', 'public_transportation_types',
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
        search_document['has_phone'] = not(not(
            document.phone or document.phone_custodian))

        return search_document

SearchWaypoint.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchWaypoint)
