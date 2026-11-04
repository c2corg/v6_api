import functools

from c2corg_api.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPNotFound
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
from c2corg_api.views import set_creator as set_creator_on_documents
from c2corg_api.views.document import (
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import article_documents_config
from c2corg_api.views.document_version import document_version
from c2corg_api.views.resource import write
from c2corg_api.views.validation import (
    validate_associations,
    validate_id,
)

validate_article_create = make_validator_create(fields_article.get('required'))
validate_article_update = make_validator_update(fields_article.get('required'))
validate_associations_create = functools.partial(
    validate_associations, ARTICLE_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, ARTICLE_TYPE, False
)


@write(
    validators=[
        body_validator(ArticleCreateSchema),
        validate_article_create,
        validate_associations_create,
    ],
    permission='authenticated',
    json=True,
)
def create_article(request):
    return create_document(request, article_schema)


@write(
    validators=[
        body_validator(ArticleUpdateSchema),
        validate_id,
        validate_article_update,
        validate_associations_update,
    ],
    permission='authenticated',
    json=True,
)
def update_article(request):
    if not request.has_permission('moderator'):
        article_id = request.validated['id']
        article = DBSession.get(Article, article_id)
        if article is None:
            raise HTTPNotFound(f'No article found for id {article_id}')
        if article.article_type == 'collab':
            article_type = request.validated['document']['article_type']
            if article_type != article.article_type:
                raise HTTPBadRequest(
                    'Article type cannot be changed for collaborative articles'
                )
        # personal articles should only be modifiable by
        # their creator and moderators
        elif not has_been_created_by(article_id, request.authenticated_userid):
            raise HTTPForbidden('No permission to change this article')
    return put_document(request, Article, article_schema)


def list_articles(request):
    return collection_get(request, ARTICLE_TYPE, article_documents_config)


def get_article(request):
    return read_document(
        request,
        article_documents_config,
        article_schema,
        include_areas=False,
        set_custom_fields=set_author,
    )


def get_article_version(request):
    return document_version(
        request, ArchiveArticle, ARTICLE_TYPE, ArchiveDocumentLocale, article_schema
    )


def get_article_info(request):
    return document_info(request, article_documents_config)


def set_author(article):
    """Set the creator (the user who created an image) on an article."""
    set_creator_on_documents([article], 'author')
