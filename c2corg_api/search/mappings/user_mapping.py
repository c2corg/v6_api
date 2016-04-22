from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta


class SearchUser(SearchDocument):
    class Meta(BaseMeta):
        doc_type = USERPROFILE_TYPE

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        for locale in document.locales:
            search_document['title_' + locale.lang] = '{0} {1}'.format(
                document.username or '', document.name or '')

        return search_document
