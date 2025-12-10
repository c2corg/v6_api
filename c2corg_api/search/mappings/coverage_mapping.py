from c2corg_api.models.coverage import COVERAGE_TYPE, Coverage
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnum


class SearchCoverage(SearchDocument):
    class Meta(BaseMeta):
        doc_type = COVERAGE_TYPE

    coverage_type = QEnum('ctyp', model_field=Coverage.coverage_type)

    FIELDS = ['coverage_type']

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(
            document, index, include_areas=False)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchCoverage.FIELDS)

        return search_document


SearchCoverage.queryable_fields = \
    QueryableMixin.get_queryable_fields(SearchCoverage)
