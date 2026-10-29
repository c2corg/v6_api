import functools

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPNotFound

from c2corg_api.models import DBSession
from c2corg_api.models.article import (
    ARTICLE_TYPE,
    ArchiveArticle,
    Article,
)
from c2corg_api.models.common.fields_article import fields_article
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.schemas.article import (
    ArticleCreateSchema,
    ArticleUpdateSchema,
    article_schema,
)
from c2corg_api.schemas.base import body_validator
from c2corg_api.views import restricted_json_view
from c2corg_api.views import set_creator as set_creator_on_documents
from c2corg_api.views.document import (
    DocumentRest,
    make_validator_create,
    make_validator_update,
)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import article_documents_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.resource import resource, view
from c2corg_api.views.validation import (
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

validate_article_create = make_validator_create(fields_article.get('required'))
validate_article_update = make_validator_update(fields_article.get('required'))
validate_associations_create = functools.partial(
    validate_associations, ARTICLE_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, ARTICLE_TYPE, False
)


@resource(collection_path='/articles', path='/articles/{id}')
class ArticleRest(DocumentRest):
    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(ARTICLE_TYPE, article_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            article_documents_config,
            article_schema,
            include_areas=False,
            set_custom_fields=set_author,
        )

    @restricted_json_view(
        validators=[
            body_validator(ArticleCreateSchema),
            validate_article_create,
            validate_associations_create,
        ],
    )
    def collection_post(self):
        return self._collection_post(article_schema)

    @restricted_json_view(
        validators=[
            body_validator(ArticleUpdateSchema),
            validate_id,
            validate_article_update,
            validate_associations_update,
        ],
    )
    def put(self):
        if not self.request.has_permission('moderator'):
            article_id = self.request.validated['id']
            article = DBSession.get(Article, article_id)
            if article is None:
                raise HTTPNotFound(f'No article found for id {article_id}')
            if article.article_type == 'collab':
                article_type = self.request.validated['document']['article_type']
                if article_type != article.article_type:
                    raise HTTPBadRequest(
                        'Article type cannot be changed for collaborative articles'
                    )
            # personal articles should only be modifiable by
            # their creator and moderators
            elif not has_been_created_by(article_id, self.request.authenticated_userid):
                raise HTTPForbidden('No permission to change this article')
        return self._put(Article, article_schema)


@resource(path='/articles/{id}/{lang}/{version_id}')
class ArticlesVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveArticle, ARTICLE_TYPE, ArchiveDocumentLocale, article_schema
        )


@resource(path='/articles/{id}/{lang}/info')
class ArticlesInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(article_documents_config)


def set_author(article):
    """Set the creator (the user who created an image) on an article."""
    set_creator_on_documents([article], 'author')
