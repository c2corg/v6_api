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
        'oac', model_field=Outing.activities)
    frequentation = QEnum(
        'of', model_field=Outing.frequentation)
    elevation_max = QInteger(
        'oe', range=True)
    height_diff_up = QInteger(
        'ohdu', range=True)
    length_total = QInteger(
        'olt', range=True)
    public_transport = QBoolean(
        'opt', is_bool=True)
    elevation_access = QInteger(
        'oea', range=True)
    elevation_up_snow = QInteger(
        'oeus', range=True)
    elevation_down_snow = QInteger(
        'oeds', range=True)
    awesomeness = QEnum(
        'oaw', model_field=Outing.awesomeness)
    condition_rating = QEnum(
        'ocr', model_field=Outing.condition_rating)
    snow_quantity = QEnum(
        'osqn', model_field=Outing.snow_quantity)
    snow_quality = QEnum(
        'osql', model_field=Outing.snow_quality)
    glacier_rating = QEnum(
        'ogr', model_field=Outing.glacier_rating)
    avalanche_signs = QEnumArray(
        'oas', model_field=Outing.avalanche_signs)

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
SearchOuting.queryable_fields['od'] = QDateRange(
    'od', 'date_start', 'date_end')
