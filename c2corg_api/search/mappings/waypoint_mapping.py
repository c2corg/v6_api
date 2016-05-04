from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger,\
    QEnumArray, QEnum, QBoolean


class SearchWaypoint(SearchDocument):
    class Meta(BaseMeta):
        doc_type = WAYPOINT_TYPE

    elevation = QInteger(
        'walt', range=True)
    waypoint_type = QEnum(
        'wtyp', model_field=Waypoint.waypoint_type)
    rock_types = QEnumArray(
        'wrock', model_field=Waypoint.rock_types)
    orientations = QEnumArray(
        'wfac', model_field=Waypoint.orientations)
    best_periods = QEnumArray(
        'period', model_field=Waypoint.best_periods)
    has_phone = QBoolean(
        'phone', is_bool=True)
    lift_access = QBoolean(
        'plift', is_bool=True)
    custodianship = QEnum(
        'hsta', model_field=Waypoint.custodianship)
    climbing_styles = QEnumArray(
        'tcsty', model_field=Waypoint.climbing_styles)
    access_time = QEnum(
        'tappt', model_field=Waypoint.access_time)
    climbing_rating_max = QEnum(
        'tmaxr', model_field=Waypoint.climbing_rating_max)
    climbing_rating_min = QEnum(
        'tminr', model_field=Waypoint.climbing_rating_min)
    climbing_rating_median = QEnum(
        'tmedr', model_field=Waypoint.climbing_rating_median)
    height_max = QInteger(
        'tmaxh', range=True)
    height_min = QInteger(
        'tminh', range=True)
    height_median = QInteger(
        'tmedh', range=True)
    routes_quantity = QInteger(
        'rqua', range=True)
    children_proof = QEnum(
        'chil', model_field=Waypoint.children_proof)
    rain_proof = QEnum(
        'rain', model_field=Waypoint.rain_proof)
    paragliding_rating = QEnum(
        'pgrat', model_field=Waypoint.paragliding_rating)
    exposition_rating = QEnum(
        'pglexp', model_field=Waypoint.exposition_rating)
    length = QInteger(
        'len', range=True)
    weather_station_types = QEnumArray(
        'whtyp', model_field=Waypoint.weather_station_types)
    capacity = QInteger(
        'hucap', range=True)
    capacity_staffed = QInteger(
        'hscap', range=True)
    equipment_ratings = QEnumArray(
        'anchq', model_field=Waypoint.equipment_ratings)
    public_transportation_types = QEnumArray(
        'tpty', model_field=Waypoint.public_transportation_types)
    public_transportation_rating = QEnum(
        'tp', model_field=Waypoint.public_transportation_rating)
    snow_clearance_rating = QEnum(
        'psnow', model_field=Waypoint.snow_clearance_rating)
    product_types = QEnumArray(
        'ftyp', model_field=Waypoint.product_types)

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
