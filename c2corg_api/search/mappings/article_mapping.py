from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnum, QEnumArray


class SearchArticle(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ARTICLE_TYPE

    activities = QEnumArray(
        'act', model_field=Article.activities)
    article_categories = QEnumArray(
        'acat', model_field=Article.categories)
    article_type = QEnum(
        'atyp', model_field=Article.article_type)

    FIELDS = ['activities', 'article_type']

    @staticmethod
    def to_search_document(document, index_prefix):
        search_document = SearchDocument.to_search_document(
            document, index_prefix)

        if document.redirects_to:
            return search_document

        search_document['article_categories'] = document.categories

        SearchDocument.copy_fields(
            search_document, document, SearchArticle.FIELDS)

        return search_document


SearchArticle.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchArticle)
