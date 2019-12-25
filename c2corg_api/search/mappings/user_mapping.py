from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin


class SearchUser(SearchDocument):
    class Meta(BaseMeta):
        doc_type = USERPROFILE_TYPE

    FIELDS = []

    @staticmethod
    def to_search_document(document, index_prefix):
        search_document = SearchDocument.to_search_document(
            document, index_prefix)

        if document.redirects_to:
            return search_document

        for locale in document.locales:
            search_document['title_' + locale.lang] = '{0} {1}'.format(
                document.name or '', document.forum_username or '')

        return search_document


SearchUser.queryable_fields = QueryableMixin.get_queryable_fields(SearchUser)
