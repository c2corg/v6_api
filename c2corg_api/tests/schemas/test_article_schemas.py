from c2corg_api.models.article import (
    Article,
    schema_article,
    schema_create_article,
    schema_listing_article,
    schema_update_article,
)
from c2corg_api.models.document import DocumentLocale
from c2corg_api.schemas.article import (
    ArticleCreateSchema,
    ArticleUpdateSchema,
    article_listing_schema,
    article_schema,
)
from c2corg_api.tests.schemas.parity import assert_document_type_parity


def test_article_parity():
    article = Article(
        document_id=1,
        version=2,
        categories=['site_info'],
        activities=['hiking'],
        article_type='collab',
        locales=[DocumentLocale(lang='en', title='Title', version=1)],
    )
    assert_document_type_parity(
        (
            schema_create_article,
            schema_update_article,
            schema_article,
            schema_listing_article,
        ),
        (
            ArticleCreateSchema,
            ArticleUpdateSchema,
            article_schema,
            article_listing_schema,
        ),
        article,
    )
