from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, QEnum, QEnumArray


class SearchArticle(SearchDocument):
    class Meta(BaseMeta):
        c2corg_doc_type = ARTICLE_TYPE

    class Index:
        name = 'c2corg_c'

    activities = QEnumArray(
        'act', model_field=Article.activities)
    article_categories = QEnumArray(
        'acat', model_field=Article.categories)
    article_type = QEnum(
        'atyp', model_field=Article.article_type)

    FIELDS = ['activities', 'article_type']

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        search_document['article_categories'] = document.categories

        SearchDocument.copy_fields(
            search_document, document, SearchArticle.FIELDS)

        return search_document


SearchArticle.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchArticle)
