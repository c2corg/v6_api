"""
FastAPI Document-Version-Mask router.

Provides ``/v2/versions/mask`` and ``/v2/versions/unmask`` —
mask or unmask a specific version of a document.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-version-mask'])


class MaskSchema(BaseModel):
    document_id: int
    lang: DefaultLangs
    version_id: int


def _validate_version(db: Session, document_id: int, lang: str, version_id: int):
    """Validate the version exists and is not the latest."""
    version_exists = db.query(
        exists().where(
            and_(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.lang == lang,
            )
        )
    ).scalar()
    if not version_exists:
        raise HTTPException(
            status_code=400,
            detail='Unknown version {}/{}/{}'.format(document_id, lang, version_id),
        )

    (latest_version_id,) = (
        db.query(DocumentVersion.id)
        .filter(
            and_(
                DocumentVersion.document_id == document_id, DocumentVersion.lang == lang
            )
        )
        .order_by(DocumentVersion.id.desc())
        .first()
    )
    if version_id == latest_version_id:
        raise HTTPException(
            status_code=400,
            detail='Version {}/{}/{} is the latest one'.format(
                document_id, lang, version_id
            ),
        )


def _get_version(db: Session, document_id: int, lang: str, version_id: int):
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(
            status_code=400, detail='Unknown version_id {}'.format(version_id)
        )
    if version.document_id != document_id or version.lang != lang:
        raise HTTPException(
            status_code=400,
            detail='Unknown version {}/{}/{}'.format(document_id, lang, version_id),
        )
    return version


@router.post('/versions/mask')
def mask_version(
    body: MaskSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Mask the given document version."""
    lang = body.lang.value if hasattr(body.lang, 'value') else body.lang
    _validate_version(db, body.document_id, lang, body.version_id)
    version = _get_version(db, body.document_id, lang, body.version_id)
    version.masked = True
    db.flush()

    update_cache_version_direct(body.document_id)

    return {}


@router.post('/versions/unmask')
def unmask_version(
    body: MaskSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Unmask the given document version."""
    lang = body.lang.value if hasattr(body.lang, 'value') else body.lang
    _validate_version(db, body.document_id, lang, body.version_id)
    version = _get_version(db, body.document_id, lang, body.version_id)
    version.masked = False
    db.flush()

    update_cache_version_direct(body.document_id)

    return {}
