from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin


class SearchTopoMap(SearchDocument):
    class Meta(BaseMeta):
        doc_type = MAP_TYPE

    FIELDS = []

    @staticmethod
    def to_search_document(document, index):
        return SearchDocument.to_search_document(document, index)

SearchTopoMap.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchTopoMap)
