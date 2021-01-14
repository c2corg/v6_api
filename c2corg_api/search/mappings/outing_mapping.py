from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QDateRange, \
    QInteger, QBoolean, QLong, QEnumArray, QEnumRange
from c2corg_common.sortable_search_attributes import \
    sortable_frequentation_types, sortable_condition_ratings, \
    sortable_snow_quality_ratings, sortable_snow_quantity_ratings, \
    sortable_glacier_ratings,\
    sortable_global_ratings, sortable_ski_ratings, \
    sortable_equipment_ratings, sortable_engagement_ratings, \
    sortable_ice_ratings, sortable_climbing_ratings, \
    sortable_via_ferrata_ratings, sortable_hiking_ratings, \
    sortable_snowshoe_ratings, sortable_mtb_up_ratings, \
    sortable_mtb_down_ratings
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

    # array of article ids
    articles = QLong('c', is_id=True)

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
        enum_mapper=sortable_snow_quantity_ratings)
    snow_quality = QEnumRange(
        'swqual', model_field=Outing.snow_quality,
        enum_mapper=sortable_snow_quality_ratings)
    glacier_rating = QEnumRange(
        'oglac', model_field=Outing.glacier_rating,
        enum_mapper=sortable_glacier_ratings)
    avalanche_signs = QEnumArray(
        'avdate', model_field=Outing.avalanche_signs)
    ski_rating = QEnumRange(
        'trat', model_field=Outing.ski_rating,
        enum_mapper=sortable_ski_ratings)
    labande_global_rating = QEnumRange(
        'lrat', model_field=Outing.labande_global_rating,
        enum_mapper=sortable_global_ratings)
    global_rating = QEnumRange(
        'grat', model_field=Outing.global_rating,
        enum_mapper=sortable_global_ratings)
    height_diff_difficulties = QInteger(
        'dhei', range=True)
    engagement_rating = QEnumRange(
        'erat', model_field=Outing.engagement_rating,
        enum_mapper=sortable_engagement_ratings)
    equipment_rating = QEnumRange(
        'prat', model_field=Outing.equipment_rating,
        enum_mapper=sortable_equipment_ratings)
    ice_rating = QEnumRange(
        'irat', model_field=Outing.ice_rating,
        enum_mapper=sortable_ice_ratings)
    rock_free_rating = QEnumRange(
        'frat', model_field=Outing.rock_free_rating,
        enum_mapper=sortable_climbing_ratings)
    via_ferrata_rating = QEnumRange(
        'krat', model_field=Outing.via_ferrata_rating,
        enum_mapper=sortable_via_ferrata_ratings)
    hiking_rating = QEnumRange(
        'hrat', model_field=Outing.hiking_rating,
        enum_mapper=sortable_hiking_ratings)
    snowshoe_rating = QEnumRange(
        'wrat', model_field=Outing.snowshoe_rating,
        enum_mapper=sortable_snowshoe_ratings)
    mtb_up_rating = QEnumRange(
        'mbur', model_field=Outing.mtb_up_rating,
        enum_mapper=sortable_mtb_up_ratings)
    mtb_down_rating = QEnumRange(
        'mbdr', model_field=Outing.mtb_down_rating,
        enum_mapper=sortable_mtb_down_ratings)

    FIELDS = [
        'activities', 'date_start', 'date_end',
        'elevation_max', 'height_diff_up', 'length_total', 'public_transport',
        'elevation_access', 'elevation_up_snow', 'elevation_down_snow',
        'avalanche_signs', 'height_diff_difficulties'
    ]

    ENUM_RANGE_FIELDS = [
        'frequentation', 'condition_rating', 'snow_quantity', 'snow_quality',
        'glacier_rating', 'hiking_rating', 'ski_rating',
        'labande_global_rating', 'ice_rating', 'snowshoe_rating',
        'global_rating',  'engagement_rating',
        'equipment_rating', 'rock_free_rating', 'via_ferrata_rating',
        'mtb_up_rating', 'mtb_down_rating'
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

        if document.associated_articles_ids:
            # add the document ids of associated routes
            search_document['articles'] = \
                document.associated_articles_ids.article_ids

        return search_document

SearchOuting.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchOuting)
SearchOuting.queryable_fields['date'] = QDateRange(
    'date', 'date_start', 'date_end')
