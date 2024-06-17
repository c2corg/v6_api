from c2corg_api.models.area import Area, AREA_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnum


class SearchArea(SearchDocument):
    class Meta(BaseMeta):
        c2corg_doc_type = AREA_TYPE

    area_type = QEnum('atyp', model_field=Area.area_type)

    FIELDS = ['area_type']

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(
            document, index, include_areas=False)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchArea.FIELDS)

        return search_document


SearchArea.queryable_fields = QueryableMixin.get_queryable_fields(SearchArea)
