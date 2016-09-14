from c2corg_api.models.article import (
    Article,
    schema_article,
    schema_update_article,
    ARTICLE_TYPE)
from c2corg_common.fields_article import fields_article
from cornice.resource import resource, view

from c2corg_api.views.document_schemas import article_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param


validate_article_create = make_validator_create(fields_article.get('required'))
validate_article_update = make_validator_update(fields_article.get('required'))


@resource(collection_path='/articles', path='/articles/{id}',
          cors_policy=cors_policy)
class ArticleRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Article, article_documents_config,
                                    ARTICLE_TYPE)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Article, schema_article)

    @restricted_json_view(
            schema=schema_article, validators=validate_article_create)
    def collection_post(self):
        return self._collection_post(schema_article)

    @restricted_json_view(
            schema=schema_update_article,
            validators=[validate_id, validate_article_update])
    def put(self):
        return self._put(Article, schema_article)
