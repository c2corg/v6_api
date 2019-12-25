from c2corg_api.models.area import AREA_TYPE, Area
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnum


class SearchArea(SearchDocument):
    class Meta(BaseMeta):
        doc_type = AREA_TYPE

    area_type = QEnum('atyp', model_field=Area.area_type)

    FIELDS = ['area_type']

    @staticmethod
    def to_search_document(document, index_prefix):
        search_document = SearchDocument.to_search_document(
            document, index_prefix, include_areas=False)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchArea.FIELDS)
        
        return search_document

SearchArea.queryable_fields = QueryableMixin.get_queryable_fields(SearchArea)
