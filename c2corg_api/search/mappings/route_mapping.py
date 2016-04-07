from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.utils import get_title


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        for locale in document.locales:
            search_document['title_' + locale.lang] = \
                get_title(locale.title, locale.title_prefix)

        return search_document
