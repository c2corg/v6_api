import functools

from c2corg_api.models import DBSession
from c2corg_api.models.article import (
    Article,
    schema_article,
    schema_create_article,
    schema_update_article,
    ARTICLE_TYPE, ArchiveArticle)
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest, HTTPForbidden

from c2corg_common.fields_article import fields_article
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.views.document_schemas import article_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations, validate_lang, validate_version_id

validate_article_create = make_validator_create(fields_article.get('required'))
validate_article_update = make_validator_update(fields_article.get('required'))
validate_associations_create = functools.partial(
    validate_associations, ARTICLE_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, ARTICLE_TYPE, False)


@resource(collection_path='/articles', path='/articles/{id}',
          cors_policy=cors_policy)
class ArticleRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(ARTICLE_TYPE, article_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Article, schema_article, include_areas=False)

    @restricted_json_view(
            schema=schema_create_article,
            validators=[
                colander_body_validator,
                validate_article_create,
                validate_associations_create])
    def collection_post(self):
        return self._collection_post(schema_article)

    @restricted_json_view(
            schema=schema_update_article,
            validators=[
                colander_body_validator,
                validate_id,
                validate_article_update,
                validate_associations_update])
    def put(self):
        if not self.request.has_permission('moderator'):
            article_id = self.request.validated['id']
            article = DBSession.query(Article).get(article_id)
            if article is None:
                raise HTTPNotFound(
                    'No article found for id {}'.format(article_id))
            if article.article_type == 'collab':
                article_type = \
                    self.request.validated['document']['article_type']
                if article_type != article.article_type:
                    raise HTTPBadRequest(
                        'Article type cannot be changed '
                        'for collaborative articles'
                    )
            # personal articles should only be modifiable by
            # their creator and moderators
            elif not has_been_created_by(article_id,
                                         self.request.authenticated_userid):
                raise HTTPForbidden('No permission to change this article')
        return self._put(Article, schema_article)


@resource(path='/articles/{id}/{lang}/{version_id}',
          cors_policy=cors_policy)
class ArticlesVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveArticle, ArchiveDocumentLocale, schema_article)


@resource(path='/articles/{id}/{lang}/info', cors_policy=cors_policy)
class ArticlesInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Article)
