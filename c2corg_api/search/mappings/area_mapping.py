from c2corg_api.models.area import AREA_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta


class SearchArea(SearchDocument):
    class Meta(BaseMeta):
        doc_type = AREA_TYPE

    @staticmethod
    def to_search_document(document, index):
        return SearchDocument.to_search_document(
            document, index, include_areas=False)
