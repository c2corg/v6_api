from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin


class SearchImage(SearchDocument):
    class Meta(BaseMeta):
        doc_type = IMAGE_TYPE

    FIELDS = []

    @staticmethod
    def to_search_document(document, index):
        return SearchDocument.to_search_document(document, index)

SearchImage.queryable_fields = QueryableMixin.get_queryable_fields(SearchImage)
