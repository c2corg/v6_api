from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnumArray, \
    QInteger, QDate


class SearchImage(SearchDocument):
    class Meta(BaseMeta):
        doc_type = IMAGE_TYPE

    activities = QEnumArray(
        'act', model_field=Image.activities)
    categories = QEnumArray(
        'cat', model_field=Image.categories)
    image_type = QEnumArray(
        'ityp', model_field=Image.image_type)
    elevation = QInteger(
        'ialt', range=True)
    date_time = QDate('idate', 'date_time')

    FIELDS = [
        'activities', 'categories', 'image_type', 'elevation', 'date_time'
    ]

    @staticmethod
    def to_search_document(document, index_prefix):
        search_document = SearchDocument.to_search_document(document, index_prefix)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchImage.FIELDS)

        return search_document

SearchImage.queryable_fields = QueryableMixin.get_queryable_fields(SearchImage)
