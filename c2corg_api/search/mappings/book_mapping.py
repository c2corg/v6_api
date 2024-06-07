from c2corg_api.models.book import BOOK_TYPE, Book
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnumArray


class SearchBook(SearchDocument):
#    class Meta(BaseMeta):
#        doc_type = BOOK_TYPE

    activities = QEnumArray(
        'act', model_field=Book.activities)
    book_types = QEnumArray(
        'btyp', model_field=Book.book_types)

    FIELDS = ['activities', 'book_types']

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchBook.FIELDS)

        return search_document


SearchBook.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchBook)
