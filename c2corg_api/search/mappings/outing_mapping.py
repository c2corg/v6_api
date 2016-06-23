from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QDateRange, \
    QInteger, QBoolean, QLong, QEnumArray, QEnumRange
from c2corg_common.sortable_search_attributes import \
    sortable_frequentation_types, sortable_condition_ratings, \
    sortable_glacier_ratings
from elasticsearch_dsl import Date


class SearchOuting(SearchDocument):
    class Meta(BaseMeta):
        doc_type = OUTING_TYPE

    date_start = Date()
    date_end = Date()

    # array of waypoint ids
    waypoints = QLong('w', is_id=True)

    # array of user ids
    users = QLong('u', is_id=True)

    # array of route ids
    routes = QLong('r', is_id=True)

    activities = QEnumArray(
        'act', model_field=Outing.activities)
    frequentation = QEnumRange(
        'ofreq', model_field=Outing.frequentation,
        enum_mapper=sortable_frequentation_types)
    elevation_max = QInteger(
        'oalt', range=True)
    height_diff_up = QInteger(
        'odif', range=True)
    length_total = QInteger(
        'olen', range=True)
    public_transport = QBoolean(
        'owpt', is_bool=True)
    elevation_access = QInteger(
        'oparka', range=True)
    elevation_up_snow = QInteger(
        'swlu', range=True)
    elevation_down_snow = QInteger(
        'swld', range=True)
    condition_rating = QEnumRange(
        'ocond', model_field=Outing.condition_rating,
        enum_mapper=sortable_condition_ratings)
    snow_quantity = QEnumRange(
        'swquan', model_field=Outing.snow_quantity,
        enum_mapper=sortable_condition_ratings)
    snow_quality = QEnumRange(
        'swqual', model_field=Outing.snow_quality,
        enum_mapper=sortable_condition_ratings)
    glacier_rating = QEnumRange(
        'oglac', model_field=Outing.glacier_rating,
        enum_mapper=sortable_glacier_ratings)
    avalanche_signs = QEnumArray(
        'avdate', model_field=Outing.avalanche_signs)

    FIELDS = [
        'activities', 'date_start', 'date_end',
        'elevation_max', 'height_diff_up', 'length_total', 'public_transport',
        'elevation_access', 'elevation_up_snow', 'elevation_down_snow',
        'avalanche_signs'
    ]

    ENUM_RANGE_FIELDS = [
        'frequentation', 'condition_rating', 'snow_quantity', 'snow_quality',
        'glacier_rating'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchOuting.FIELDS)

        SearchDocument.copy_enum_range_fields(
            search_document, document, SearchOuting.ENUM_RANGE_FIELDS,
            SearchOuting)

        if document.associated_waypoints_ids:
            # add the document ids of associated waypoints and of the parent
            # and grand-parents of these waypoints
            search_document['waypoints'] = \
                document.associated_waypoints_ids.waypoint_ids

        if document.associated_users_ids:
            # add the document ids of associated users
            search_document['users'] = \
                document.associated_users_ids.user_ids

        if document.associated_routes_ids:
            # add the document ids of associated routes
            search_document['routes'] = \
                document.associated_routes_ids.route_ids

        return search_document

SearchOuting.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchOuting)
SearchOuting.queryable_fields['date'] = QDateRange(
    'date', 'date_start', 'date_end')
