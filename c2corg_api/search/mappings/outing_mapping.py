from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta, Enum, EnumArray
from elasticsearch_dsl import Integer, Date, Boolean


class SearchOuting(SearchDocument):
    class Meta(BaseMeta):
        doc_type = OUTING_TYPE

    activities = EnumArray()
    date_start = Date()
    date_end = Date()
    frequentation = Enum()
    elevation_max = Integer()
    height_diff_up = Integer()
    length_total = Integer()
    public_transport = Boolean()
    elevation_access = Integer()
    elevation_up_snow = Integer()
    elevation_down_snow = Integer()
    awesomeness = Enum()
    condition_rating = Enum()
    snow_quantity = Enum()
    snow_quality = Enum()
    glacier_rating = Enum()
    avalanche_signs = EnumArray()

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
