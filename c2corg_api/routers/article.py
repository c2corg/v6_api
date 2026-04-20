"""
FastAPI Article router.

Handles GET (single + collection), POST, PUT, version retrieval and
document info for articles.

During the transition both this router **and** the legacy
``c2corg_api.views.article.ArticleRest`` coexist.  The FastAPI routes
are served under ``/v2/articles`` so that the legacy ``/articles``
Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.article import ARTICLE_TYPE, ArchiveArticle, Article
from c2corg_api.models.article import attributes as article_attributes
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_helpers import (
    set_creator as set_creator_on_documents,
)
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import article_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.article import (
    ArticleReadSchema,
    CreateArticleSchema,
    UpdateArticleSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/articles', tags=['articles'])

# The fields required on create/update for articles
REQUIRED_FIELDS = ['locales', 'locales.title', 'article_type']


def _set_author(article):
    """Set the creator (first version) as author."""
    set_creator_on_documents([article], 'author')


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/articles
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_articles(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of articles."""
    return get_document_collection(
        article_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/articles/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_article(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single article."""
    return get_single_document(
        Article,
        document_id,
        document_type=ARTICLE_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=ArticleReadSchema,
        include_areas=False,
        set_custom_fields=_set_author,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────────────
# POST  — /v2/articles
# ──────────────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_article(
    body: CreateArticleSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new article document."""
    return create_document(
        model_class=Article,
        body_schema=body,
        document_type=ARTICLE_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
    )


# ──────────────────────────────────────────────────────────────────────
# PUT  — /v2/articles/{id}
# ──────────────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_article(
    document_id: DocumentId,
    body: UpdateArticleSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing article.

    Articles have special permission rules:
    - Collaborative articles can be edited by anyone, but their type
      cannot be changed to personal by non-moderators.
    - Personal articles can only be edited by their creator or moderators.
    """
    if not user.moderator:
        article = db.get(Article, document_id)
        if article is None:
            raise HTTPException(
                status_code=404,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'name': 'Not Found',
                            'description': f'No article found for id {document_id}',
                            'location': 'url',
                        }
                    ],
                },
            )
        if article.article_type == 'collab':
            new_article_type = body.document.article_type
            if new_article_type and new_article_type != article.article_type:
                raise HTTPException(
                    status_code=400,
                    detail={
                        'status': 'error',
                        'errors': [
                            {
                                'name': 'Bad Request',
                                'description': 'Article type cannot be changed '
                                'for collaborative articles',
                                'location': 'body',
                            }
                        ],
                    },
                )
        elif not has_been_created_by(document_id, user.id, db=db):
            raise HTTPException(
                status_code=403,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'name': 'Forbidden',
                            'description': 'No permission to change this article',
                            'location': 'body',
                        }
                    ],
                },
            )

    return update_document(
        document_id=document_id,
        model_class=Article,
        body_schema=body,
        document_type=ARTICLE_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=article_attributes,
        user=user,
        db=db,
    )


# ──────────────────────────────────────────────────────────────────────
# GET info — /v2/articles/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_article_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Article, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────────────
# GET version — /v2/articles/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_article_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of an article document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=ARTICLE_TYPE,
        archive_model=ArchiveArticle,
        read_schema=ArticleReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
