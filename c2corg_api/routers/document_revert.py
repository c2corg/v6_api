"""
FastAPI Document-Revert router.

Provides ``/v2/documents/revert`` — revert a document to a previous
version.
"""

import logging

from c2corg_api.models import DBSession
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, exists
from sqlalchemy.orm import Session, contains_eager, joinedload, with_polymorphic

from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE, ArchiveArea, Area
from c2corg_api.models.article import ARTICLE_TYPE, ArchiveArticle, Article
from c2corg_api.models.book import BOOK_TYPE, ArchiveBook, Book
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import ArchiveDocumentLocale, Document, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import IMAGE_TYPE, ArchiveImage, Image
from c2corg_api.models.outing import (
    OUTING_TYPE,
    ArchiveOuting,
    ArchiveOutingLocale,
    Outing,
    OutingLocale,
)
from c2corg_api.models.route import (
    ROUTE_TYPE,
    ArchiveRoute,
    ArchiveRouteLocale,
    Route,
    RouteLocale,
)
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE,
    ArchiveWaypoint,
    ArchiveWaypointLocale,
    Waypoint,
    WaypointLocale,
)
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    ArchiveXreport,
    ArchiveXreportLocale,
    Xreport,
    XreportLocale,
)
from c2corg_api.routers.helpers.document_crud import revert_update_document
from c2corg_api.routers.helpers.linked_attributes import (
    update_area_associations as update_associations,
)
from c2corg_api.routers.helpers.linked_attributes import (
    update_linked_attributes,
    update_linked_route_titles,
)
from c2corg_api.security.fastapi_security import require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-revert'])


class RevertSchema(BaseModel):
    document_id: int
    lang: DefaultLangs
    version_id: int


def _get_models(document_id):
    (document_type,) = (
        DBSession
        .query(Document.type)
        .filter(Document.document_id == document_id)
        .first()
    )

    if document_type == WAYPOINT_TYPE:
        return (
            Waypoint,
            WaypointLocale,
            ArchiveWaypoint,
            ArchiveWaypointLocale,
            document_type,
        )
    if document_type == ROUTE_TYPE:
        return (Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale, document_type)
    if document_type == OUTING_TYPE:
        return (Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale, document_type)
    if document_type == IMAGE_TYPE:
        return (Image, None, ArchiveImage, ArchiveDocumentLocale, document_type)
    if document_type == ARTICLE_TYPE:
        return (Article, None, ArchiveArticle, ArchiveDocumentLocale, document_type)
    if document_type == BOOK_TYPE:
        return (Book, None, ArchiveBook, ArchiveDocumentLocale, document_type)
    if document_type == XREPORT_TYPE:
        return (
            Xreport,
            XreportLocale,
            ArchiveXreport,
            ArchiveXreportLocale,
            document_type,
        )
    if document_type == AREA_TYPE:
        return (Area, None, ArchiveArea, ArchiveDocumentLocale, document_type)
    assert False


def _get_archive_document(
    document_id, lang, version_id, archive_clazz, archive_locale_clazz
):
    version = (
        DBSession
        .query(DocumentVersion)
        .options(joinedload(DocumentVersion.document_archive.of_type(archive_clazz)))
        .options(
            joinedload(
                DocumentVersion.document_locales_archive.of_type(archive_locale_clazz)
            )
        )
        .options(joinedload(DocumentVersion.document_geometry_archive))
        .filter(DocumentVersion.id == version_id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .first()
    )

    archive_document = version.document_archive
    archive_document.geometry = version.document_geometry_archive
    archive_document.locales = [version.document_locales_archive]
    return archive_document


def _get_current_document(document_id, lang, clazz, clazz_locale):
    locales_type = (
        with_polymorphic(DocumentLocale, clazz_locale)
        if clazz_locale
        else DocumentLocale
    )
    locales_attr = getattr(clazz, 'locales')
    locales_type_eager = (
        locales_attr.of_type(clazz_locale) if clazz_locale else locales_attr
    )

    document_query = (
        DBSession
        .query(clazz)
        .join(locales_type)
        .filter(getattr(clazz, 'document_id') == document_id)
        .filter(DocumentLocale.lang == lang)
        .options(joinedload(clazz.geometry))
        .options(contains_eager(locales_type_eager, alias=locales_type))
    )
    return document_query.first()


def _get_after_update(document_type):
    if document_type == WAYPOINT_TYPE:
        return update_linked_route_titles
    if document_type == ROUTE_TYPE:
        return update_linked_attributes
    if document_type == AREA_TYPE:
        return update_associations
    return None


@router.post('/documents/revert')
def revert_document(
    body: RevertSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Revert a document to a previous version."""
    document_id = body.document_id
    lang = body.lang.value if hasattr(body.lang, 'value') else body.lang
    version_id = body.version_id

    # Validate version exists
    version_exists = (
        DBSession
        .query(
            exists().where(
                and_(
                    DocumentVersion.id == version_id,
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.lang == lang,
                )
            )
        )
        .scalar()
    )
    if not version_exists:
        raise HTTPException(
            status_code=400,
            detail='Unknown version {}/{}/{}'.format(document_id, lang, version_id),
        )

    # Check not the latest
    (last_version_id,) = (
        DBSession
        .query(DocumentVersion.id)
        .filter(
            and_(
                DocumentVersion.document_id == document_id, DocumentVersion.lang == lang
            )
        )
        .order_by(DocumentVersion.id.desc())
        .first()
    )

    if version_id == last_version_id:
        raise HTTPException(
            status_code=400,
            detail='Version {}/{}/{} is already the latest one'.format(
                document_id, lang, version_id
            ),
        )

    clazz, locale_clazz, archive_clazz, archive_locale_clazz, document_type = (
        _get_models(document_id)
    )

    document = _get_current_document(document_id, lang, clazz, locale_clazz)
    document_in = _get_archive_document(
        document_id, lang, version_id, archive_clazz, archive_locale_clazz
    )

    before_update = None
    after_update = _get_after_update(document_type)

    def manage_versions(document, old_versions):
        document.version = old_versions['document']
        document.locales[0].version = old_versions['locales'][lang]
        if document.geometry:
            document.geometry.version = old_versions['geometry']

    update_types = revert_update_document(
        document,
        document_in,
        user_id=user.id,
        is_moderator=True,
        message='Revert to version {}'.format(version_id),
        before_update=before_update,
        after_update=after_update,
        manage_versions=manage_versions,
    )

    if not update_types:
        raise HTTPException(
            status_code=400, detail='No change to apply when reverting to this version'
        )

    return {}
