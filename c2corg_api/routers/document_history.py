"""
FastAPI Document-History router.

Provides ``/v2/document/{id}/history/{lang}`` — returns the version
history of a document in a given language.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session, joinedload

from c2corg_api.database import get_db
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import DOCUMENT_TYPE, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.routers.helpers.document_version import serialize_version

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-history'])


@router.get('/document/{id}/history/{lang}')
def get_document_history(
    id: int = Path(..., ge=0), lang: str = Path(...), db: Session = Depends(get_db)
):
    """Return the version history of a document for a given language."""
    # Validate lang
    if lang not in [e.value for e in DefaultLangs]:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'lang',
                        'description': 'invalid lang',
                        'location': 'querystring',
                    }
                ]
            },
        )

    # Check cache version exists for this document
    cache_key = get_cache_key(id, lang, document_type=DOCUMENT_TYPE)

    if not cache_key:
        raise HTTPException(
            status_code=404, detail='no version for document {0}'.format(id)
        )

    title = (
        db.query(DocumentLocale.title)
        .filter(DocumentLocale.document_id == id)
        .filter(DocumentLocale.lang == lang)
        .first()
    )

    if not title:
        raise HTTPException(
            status_code=404, detail='no locale document for "{0}"'.format(lang)
        )

    versions = (
        db.query(DocumentVersion)
        .options(
            joinedload(DocumentVersion.history_metadata).joinedload(
                HistoryMetaData.user
            )
        )
        .filter(DocumentVersion.document_id == id)
        .filter(DocumentVersion.lang == lang)
        .order_by(DocumentVersion.id)
        .all()
    )

    return {'title': title.title, 'versions': [serialize_version(v) for v in versions]}
