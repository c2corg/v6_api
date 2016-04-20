from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.search.mapping import SearchDocument, BaseMeta, \
    QEnumArray, QEnum
from c2corg_api.search.mapping_types import QueryableMixin, QDateRange, \
    QInteger, QBoolean
from elasticsearch_dsl import Date


class SearchOuting(SearchDocument):
    class Meta(BaseMeta):
        doc_type = OUTING_TYPE

    date_start = Date()
    date_end = Date()

    activities = QEnumArray(
        'ac', model_field=Outing.activities)
    frequentation = QEnum(
        'f', model_field=Outing.frequentation)
    elevation_max = QInteger(
        'e', range=True)
    height_diff_up = QInteger(
        'hdu', range=True)
    length_total = QInteger(
        'lt', range=True)
    public_transport = QBoolean(
        'pt', is_bool=True)
    elevation_access = QInteger(
        'ea', range=True)
    elevation_up_snow = QInteger(
        'eus', range=True)
    elevation_down_snow = QInteger(
        'eds', range=True)
    awesomeness = QEnum(
        'aw', model_field=Outing.awesomeness)
    condition_rating = QEnum(
        'cr', model_field=Outing.condition_rating)
    snow_quantity = QEnum(
        'sqn', model_field=Outing.snow_quantity)
    snow_quality = QEnum(
        'sql', model_field=Outing.snow_quality)
    glacier_rating = QEnum(
        'gr', model_field=Outing.glacier_rating)
    avalanche_signs = QEnumArray(
        'as', model_field=Outing.avalanche_signs)

    FIELDS = [
        'activities', 'date_start', 'date_end', 'frequentation',
        'elevation_max', 'height_diff_up', 'length_total', 'public_transport',
        'elevation_access', 'elevation_up_snow', 'elevation_down_snow',
        'awesomeness', 'condition_rating', 'snow_quantity', 'snow_quality',
        'glacier_rating', 'avalanche_signs'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchOuting.FIELDS)

        return search_document

SearchOuting.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchOuting)
SearchOuting.queryable_fields['d'] = QDateRange('d', 'date_start', 'date_end')
