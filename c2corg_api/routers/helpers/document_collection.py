"""
Shared helper for the ``GET /`` collection endpoint.

This is the FastAPI equivalent of the legacy
``c2corg_api.views.document.DocumentRest._collection_get``.

When the request carries ES search parameters (any query-string key
that is *not* ``offset``, ``limit``, or ``pl``), the document IDs are
fetched from ElasticSearch via :func:`advanced_search.get_search_documents`.
Otherwise they are loaded straight from the database (the fast path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy.orm import Session, load_only

from c2corg_api.models.document import Document
from c2corg_api.routers.helpers.document_listings import get_documents
from c2corg_api.search import advanced_search

if TYPE_CHECKING:
    from starlette.requests import Request

# Defaults (same as the Pyramid codebase)
LIMIT_MAX = 100
LIMIT_DEFAULT = 30
ES_MAX_RESULT_WINDOW = 10000


def get_document_collection(
    documents_config,
    *,
    offset: int = 0,
    limit: int = LIMIT_DEFAULT,
    preferred_lang: str | None = None,
    db: Session,
    request: Request | None = None,
):
    """Return a paginated list of documents.

    Parameters
    ----------
    documents_config
        A ``GetDocumentsConfig`` instance (from ``document_schemas``).
    offset / limit
        Pagination.
    preferred_lang
        Value of the ``?pl=`` query parameter.
    db
        Active SA session.
    request
        The incoming FastAPI ``Request``.  When present its query
        parameters are inspected for ES search filters (``wtyp``,
        ``act``, ``bbox``, ``q``, …).  If any are found the document
        IDs are fetched from ElasticSearch instead of the database.
    """
    limit = min(limit, LIMIT_MAX)

    if offset + limit > ES_MAX_RESULT_WINDOW:
        raise HTTPException(
            status_code=400,
            detail='offset + limit greater than {}'.format(ES_MAX_RESULT_WINDOW),
        )

    meta_params = {'offset': offset, 'limit': limit, 'lang': preferred_lang}

    # Determine whether to use ES or the plain DB path.
    url_params = dict(request.query_params) if request is not None else {}
    doc_type = documents_config.document_type

    if advanced_search.contains_search_params(url_params):
        # ES path — identical to Pyramid's ``_collection_get``
        search_documents_fn = advanced_search.get_search_documents(
            url_params, meta_params, doc_type
        )
    else:
        # DB path — simple paginated query
        def search_documents_fn(base_query, base_total_query):
            documents = (
                base_query.options(
                    load_only(Document.document_id, Document.type, Document.version)
                )
                .slice(offset, offset + limit)
                .limit(limit)
                .all()
            )
            total = base_total_query.count()
            document_ids = [doc.document_id for doc in documents]
            return document_ids, total

    return get_documents(documents_config, meta_params, search_documents_fn, db=db)
