from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QInteger,\
    QEnumArray, QEnum, QBoolean, QEnumRange
from c2corg_common.sortable_search_attributes import sortable_access_times, \
    sortable_climbing_ratings, sortable_paragliding_ratings, \
    sortable_exposition_ratings, sortable_equipment_ratings


class SearchWaypoint(SearchDocument):
    class Meta(BaseMeta):
        doc_type = WAYPOINT_TYPE

    elevation = QInteger(
        'walt', range=True)
    prominence = QInteger(
        'prom', range=True)
    waypoint_type = QEnum(
        'wtyp', model_field=Waypoint.waypoint_type)
    rock_types = QEnumArray(
        'wrock', model_field=Waypoint.rock_types)
    orientations = QEnumArray(
        'wfac', model_field=Waypoint.orientations)
    best_periods = QEnumArray(
        'period', model_field=Waypoint.best_periods)
    lift_access = QBoolean(
        'plift', is_bool=True)
    custodianship = QEnum(
        'hsta', model_field=Waypoint.custodianship)
    climbing_styles = QEnumArray(
        'tcsty', model_field=Waypoint.climbing_styles)
    access_time = QEnumRange(
        'tappt', model_field=Waypoint.access_time,
        enum_mapper=sortable_access_times)
    climbing_rating_max = QEnumRange(
        'tmaxr', model_field=Waypoint.climbing_rating_max,
        enum_mapper=sortable_climbing_ratings)
    climbing_rating_min = QEnumRange(
        'tminr', model_field=Waypoint.climbing_rating_min,
        enum_mapper=sortable_climbing_ratings)
    climbing_rating_median = QEnumRange(
        'tmedr', model_field=Waypoint.climbing_rating_median,
        enum_mapper=sortable_climbing_ratings)
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
    climbing_outdoor_types = QEnumArray(
        'ctout', model_field=Waypoint.climbing_outdoor_types)
    climbing_indoor_types = QEnumArray(
        'ctin', model_field=Waypoint.climbing_indoor_types)
    paragliding_rating = QEnumRange(
        'pgrat', model_field=Waypoint.paragliding_rating,
        enum_mapper=sortable_paragliding_ratings)
    exposition_rating = QEnumRange(
        'pglexp', model_field=Waypoint.exposition_rating,
        enum_mapper=sortable_exposition_ratings)
    length = QInteger(
        'len', range=True)
    weather_station_types = QEnumArray(
        'whtyp', model_field=Waypoint.weather_station_types)
    capacity = QInteger(
        'hucap', range=True)
    capacity_staffed = QInteger(
        'hscap', range=True)
    equipment_ratings = QEnumRange(
        'anchq', model_field=Waypoint.equipment_ratings,
        enum_mapper=sortable_equipment_ratings)
    public_transportation_types = QEnumArray(
        'tpty', model_field=Waypoint.public_transportation_types)
    public_transportation_rating = QEnum(
        'tp', model_field=Waypoint.public_transportation_rating)
    snow_clearance_rating = QEnum(
        'psnow', model_field=Waypoint.snow_clearance_rating)
    product_types = QEnumArray(
        'ftyp', model_field=Waypoint.product_types)

    FIELDS = [
        'elevation', 'prominence', 'waypoint_type', 'rock_types',
        'orientations', 'climbing_outdoor_types', 'climbing_indoor_types',
        'best_periods', 'lift_access', 'custodianship', 'climbing_styles',
        'height_max', 'height_min', 'height_median',
        'routes_quantity', 'children_proof', 'rain_proof',
        'length', 'weather_station_types', 'capacity', 'capacity_staffed',
        'public_transportation_types', 'public_transportation_rating',
        'snow_clearance_rating', 'product_types'
    ]

    ENUM_RANGE_FIELDS = [
        'access_time', 'climbing_rating_max', 'climbing_rating_min',
        'climbing_rating_median', 'paragliding_rating', 'exposition_rating',
        'equipment_ratings'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchWaypoint.FIELDS)

        SearchDocument.copy_enum_range_fields(
            search_document, document, SearchWaypoint.ENUM_RANGE_FIELDS,
            SearchWaypoint)

        return search_document

SearchWaypoint.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchWaypoint)
