"""
FastAPI Document-Delete router.

Provides ``/v2/documents/delete/{id}`` and
``/v2/documents/delete/{id}/{lang}`` — delete a document or a single
locale of a document.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import and_, exists, func, or_, over, select
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models import article, image
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import ARTICLE_TYPE, ArchiveArticle, Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import BOOK_TYPE, ArchiveBook, Book
from c2corg_api.models.cache_version import CacheVersion, update_cache_version_full
from c2corg_api.models.coverage import COVERAGE_TYPE, Coverage
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
    get_available_langs,
)
from c2corg_api.models.document_history import (
    DocumentVersion,
    HistoryMetaData,
    has_been_created_by,
    is_less_than_24h_old,
)
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.feed import DocumentChange, update_langs_of_changes
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
from c2corg_api.models.topo_map_association import TopoMapAssociation
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
from c2corg_api.search.notify_sync import notify_es_syncer_immediate
from c2corg_api.security.fastapi_security import get_current_user, require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-delete'])

_queue_config = None


def configure_delete_router(queue_config):
    global _queue_config
    _queue_config = queue_config


# ------------------------------------------------------------------
# Supported document types for deletion
# ------------------------------------------------------------------
_DELETABLE_TYPES = frozenset(
    [
        WAYPOINT_TYPE,
        ROUTE_TYPE,
        OUTING_TYPE,
        IMAGE_TYPE,
        ARTICLE_TYPE,
        BOOK_TYPE,
        XREPORT_TYPE,
        COVERAGE_TYPE,
    ]
)


def _get_document_type(document_id):
    doc = (
        resolve_db(None)
        .query(Document.type)
        .filter(Document.document_id == document_id)
        .first()
    )
    if not doc:
        return None
    return doc.type


def _is_main_waypoint_of_route(document_id):
    return (
        resolve_db(None)
        .query(exists().where(Route.main_waypoint_id == document_id))
        .scalar()
    )


def _is_only_waypoint_of_route(document_id):
    routes = (
        resolve_db(None)
        .query(Association.child_document_id)
        .filter(
            and_(
                Association.parent_document_id == document_id,
                Association.child_document_type == ROUTE_TYPE,
            )
        )
        .subquery()
    )
    only_waypoint = (
        resolve_db(None)
        .query(Association)
        .filter(
            and_(
                Association.child_document_id == routes.c.child_document_id,
                Association.parent_document_type == WAYPOINT_TYPE,
            )
        )
        .group_by(Association.child_document_id)
        .having(func.count('*') == 1)
        .exists()
    )
    return resolve_db(None).query(only_waypoint).scalar()


def _is_only_route_of_outing(document_id):
    outings = (
        resolve_db(None)
        .query(Association.child_document_id)
        .filter(
            and_(
                Association.parent_document_id == document_id,
                Association.child_document_type == OUTING_TYPE,
            )
        )
        .subquery()
    )
    only_route = (
        resolve_db(None)
        .query(Association)
        .filter(
            and_(
                Association.child_document_id == outings.c.child_document_id,
                Association.parent_document_type == ROUTE_TYPE,
            )
        )
        .group_by(Association.child_document_id)
        .having(func.count('*') == 1)
        .exists()
    )
    return resolve_db(None).query(only_route).scalar()


def _validate_delete(document_id, document_type, user, lang=None):
    """Run all validation checks. Returns (is_only_locale,) or raises."""
    errors = []

    is_only_locale = None
    if lang is not None:
        available = get_available_langs(document_id)
        if lang not in available:
            errors.append(
                {
                    'name': 'lang',
                    'location': 'querystring',
                    'description': 'locale not found',
                }
            )
            raise HTTPException(status_code=400, detail={'errors': errors})
        is_only_locale = len(available) == 1
        if not is_only_locale:
            return is_only_locale

    if document_type == WAYPOINT_TYPE:
        if _is_main_waypoint_of_route(document_id):
            errors.append(
                {
                    'name': 'document_id',
                    'location': 'querystring',
                    'description': (
                        'This waypoint cannot be deleted because it is a main waypoint.'
                    ),
                }
            )
        elif _is_only_waypoint_of_route(document_id):
            errors.append(
                {
                    'name': 'document_id',
                    'location': 'querystring',
                    'description': (
                        'This waypoint cannot be deleted because '
                        'it is the only waypoint associated to '
                        'some routes.'
                    ),
                }
            )
    elif document_type == ROUTE_TYPE:
        if _is_only_route_of_outing(document_id):
            errors.append(
                {
                    'name': 'document_id',
                    'location': 'querystring',
                    'description': (
                        'This route cannot be deleted because '
                        'it is the only route associated to '
                        'some outings.'
                    ),
                }
            )

    if errors:
        raise HTTPException(status_code=400, detail={'errors': errors})

    return is_only_locale


def _validate_requestor(document_id, document_type, user):
    """Check the requestor has permission to delete."""
    if user.moderator:
        return

    # Only personal documents might be deleted by non-moderators
    if document_type in (WAYPOINT_TYPE, ROUTE_TYPE, BOOK_TYPE):
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_type',
                        'location': 'querystring',
                        'description': ('No permission to delete this document'),
                    }
                ]
            },
        )

    if not is_less_than_24h_old(document_id):
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'location': 'querystring',
                        'description': (
                            'Only document less than 24h old can be deleted'
                        ),
                    }
                ]
            },
        )

    user_id = user.id

    if document_type in (OUTING_TYPE, XREPORT_TYPE):
        if not has_been_created_by(document_id, user_id):
            raise HTTPException(
                status_code=400,
                detail={
                    'errors': [
                        {
                            'name': 'document_id',
                            'location': 'querystring',
                            'description': (
                                'Only the initial author can delete this document'
                            ),
                        }
                    ]
                },
            )
        return

    if (
        (document_type == IMAGE_TYPE and image.is_personal(document_id))
        or (document_type == ARTICLE_TYPE and article.is_personal(document_id))
    ) and has_been_created_by(document_id, user_id):
        return

    raise HTTPException(
        status_code=400,
        detail={
            'errors': [
                {
                    'name': 'document_id',
                    'location': 'querystring',
                    'description': ('No permission to delete this document'),
                }
            ]
        },
    )


# ------------------------------------------------------------------
# Core delete logic (re-uses Pyramid helpers via DBSession)
# ------------------------------------------------------------------


def _get_models(document_type):
    if document_type == WAYPOINT_TYPE:
        return (Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)
    if document_type == ROUTE_TYPE:
        return (Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
    if document_type == OUTING_TYPE:
        return (Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)
    if document_type == IMAGE_TYPE:
        return Image, None, ArchiveImage, None
    if document_type == ARTICLE_TYPE:
        return Article, None, ArchiveArticle, None
    if document_type == BOOK_TYPE:
        return Book, None, ArchiveBook, None
    if document_type == COVERAGE_TYPE:
        return Coverage, None, ArchiveDocument, None
    if document_type == XREPORT_TYPE:
        return (Xreport, XreportLocale, ArchiveXreport, ArchiveXreportLocale)
    assert False


def _get_settings():
    from c2corg_api.routers.helpers.document_crud import _load_settings_once

    return _load_settings_once()


def _delete_image_files_immediate(document_id, settings):
    """Delete all files for an image by POSTing to the image backend.

    Unlike the Pyramid helper ``delete_all_files_for_image`` this fires
    *immediately* — no ``run_on_successful_transaction`` wrapper — because
    the FastAPI code path commits the DB session itself and there is no
    ``zope.transaction`` involved.

    Errors are logged but intentionally **not** raised, so a backend
    failure does not prevent the document deletion from succeeding.
    """
    import requests as http_requests

    filenames_result = (
        resolve_db(None)
        .query(ArchiveImage.filename)
        .filter(ArchiveImage.document_id == document_id)
        .group_by(ArchiveImage.filename)
        .all()
    )
    filenames = [f for (f,) in filenames_result]
    if not filenames:
        return

    url = '{}/{}'.format(settings.get('image_backend.url', ''), 'delete')
    secret = settings.get('image_backend.secret_key', '')

    try:
        resp = http_requests.post(url, data={'secret': secret, 'filenames': filenames})
        if resp.status_code != 200:
            log.warning(
                'Deleting image files for document %s failed: %s %s',
                document_id,
                resp.status_code,
                resp.reason,
            )
    except Exception:
        log.error(
            'Error deleting image files for document %s', document_id, exc_info=True
        )


def _delete_document(document_id, document_type, redirecting=False):
    """Recursive delete — mirrors DeleteBase._delete_document."""
    # Handle merged docs first
    merged_ids = (
        resolve_db(None)
        .query(ArchiveDocument.document_id)
        .filter(ArchiveDocument.redirects_to == document_id)
        .all()
    )
    for (mid,) in merged_ids:
        _delete_document(mid, document_type, True)

    # Remove from cache
    resolve_db(None).query(CacheVersion).filter(
        CacheVersion.document_id == document_id
    ).delete()

    update_cache_version_full(document_id, document_type)
    _remove_associations(document_id)
    _remove_tags(document_id)

    clazz, clazz_locale, archive_clazz, archive_clazz_locale = _get_models(
        document_type
    )

    if not redirecting:
        _remove_from_feed(document_id)

    if not redirecting and document_type == IMAGE_TYPE:
        _remove_image_from_feed(document_id)

    if document_type == WAYPOINT_TYPE:
        _remove_wp_from_routes_archives(document_id)

    _remove_whole_document(
        document_id, clazz, clazz_locale, archive_clazz, archive_clazz_locale
    )


def _do_delete(document_id, document_type, settings):
    if document_type == IMAGE_TYPE:
        _delete_image_files_immediate(document_id, settings)

    _delete_document(document_id, document_type)

    resolve_db(None).add(ESDeletedDocument(document_id=document_id, type=document_type))

    if _queue_config:
        notify_es_syncer_immediate(_queue_config)

    return {}


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.delete('/documents/delete/{id}')
def delete_document(
    id: int = Path(..., ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a document."""
    document_type = _get_document_type(id)
    if not document_type:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'location': 'querystring',
                        'description': 'document not found',
                    }
                ]
            },
        )
    if document_type not in _DELETABLE_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'location': 'querystring',
                        'description': ('Unsupported type when deleting document'),
                    }
                ]
            },
        )

    _validate_requestor(id, document_type, user)
    _validate_delete(id, document_type, user)

    return _do_delete(id, document_type, _get_settings())


@router.delete('/documents/delete/{id}/{lang}')
def delete_document_locale(
    id: int = Path(..., ge=0),
    lang: str = Path(...),
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Delete a document locale."""
    document_type = _get_document_type(id)
    if not document_type:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'location': 'querystring',
                        'description': 'document not found',
                    }
                ]
            },
        )
    if document_type not in _DELETABLE_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'location': 'querystring',
                        'description': ('Unsupported type when deleting document'),
                    }
                ]
            },
        )

    is_only_locale = _validate_delete(id, document_type, user, lang=lang)

    if is_only_locale:
        return _do_delete(id, document_type, _get_settings())

    clazz, clazz_locale, archive_clazz, archive_clazz_locale = _get_models(
        document_type
    )

    _remove_locale_versions(id, lang)
    _remove_archive_locale(archive_clazz_locale, id, lang)
    _remove_locale(clazz_locale, id, lang)
    update_langs_of_changes(id)

    update_cache_version_full(id, document_type)

    resolve_db(None).add(ESDeletedLocale(document_id=id, type=document_type, lang=lang))

    if _queue_config:
        notify_es_syncer_immediate(_queue_config)

    return {}


# ------------------------------------------------------------------
# Low-level helpers — mirror the Pyramid view helpers exactly
# ------------------------------------------------------------------


def _remove_whole_document(
    document_id, clazz, clazz_locale, archive_clazz, archive_clazz_locale
):
    _remove_versions(document_id)
    _remove_archive_locale(archive_clazz_locale, document_id)
    _remove_archive_geometry(document_id)
    _remove_archive(archive_clazz, document_id)
    _remove_locale(clazz_locale, document_id)
    _remove_geometry(document_id)
    _remove_figures(clazz, document_id)
    _remove_associations(document_id)
    _remove_document(document_id)


def _remove_versions(document_id):
    history_metadata_ids = [
        mid
        for (mid,) in resolve_db(None)
        .query(DocumentVersion.history_metadata_id)
        .filter(DocumentVersion.document_id == document_id)
        .all()
    ]
    resolve_db(None).query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).delete()
    if history_metadata_ids:
        resolve_db(None).execute(
            HistoryMetaData.__table__.delete().where(
                HistoryMetaData.id.in_(history_metadata_ids)
            )
        )


def _remove_locale_versions(document_id, lang):
    t = (
        resolve_db(None)
        .query(
            DocumentVersion.history_metadata_id,
            DocumentVersion.lang,
            over(
                func.count('*'), partition_by=DocumentVersion.history_metadata_id
            ).label('cnt'),
        )
        .filter(DocumentVersion.document_id == document_id)
        .subquery('t')
    )

    history_metadata_ids = [
        mid
        for (mid,) in resolve_db(None)
        .query(t.c.history_metadata_id)
        .filter(t.c.lang == lang)
        .filter(t.c.cnt == 1)
        .all()
    ]

    resolve_db(None).query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).filter(DocumentVersion.lang == lang).delete()

    if history_metadata_ids:
        resolve_db(None).execute(
            HistoryMetaData.__table__.delete().where(
                HistoryMetaData.id.in_(history_metadata_ids)
            )
        )


def _remove_archive_locale(archive_clazz_locale, document_id, lang=None):
    if archive_clazz_locale:
        locale_filter = ArchiveDocumentLocale.document_id == document_id
        if lang:
            locale_filter = and_(locale_filter, ArchiveDocumentLocale.lang == lang)
        archive_locale_ids = select(ArchiveDocumentLocale.id).where(locale_filter)
        resolve_db(None).execute(
            archive_clazz_locale.__table__.delete().where(
                getattr(archive_clazz_locale, 'id').in_(archive_locale_ids)
            )
        )

    query = (
        resolve_db(None)
        .query(ArchiveDocumentLocale)
        .filter(ArchiveDocumentLocale.document_id == document_id)
    )
    if lang:
        query = query.filter(ArchiveDocumentLocale.lang == lang)
    query.delete()


def _remove_locale(clazz_locale, document_id, lang=None):
    locale_filter = DocumentLocale.document_id == document_id
    if lang:
        locale_filter = and_(locale_filter, DocumentLocale.lang == lang)
    document_locale_ids = select(DocumentLocale.id).where(locale_filter)

    resolve_db(None).execute(
        DocumentTopic.__table__.delete().where(
            DocumentTopic.document_locale_id.in_(document_locale_ids)
        )
    )

    if clazz_locale:
        resolve_db(None).execute(
            clazz_locale.__table__.delete().where(
                getattr(clazz_locale, 'id').in_(document_locale_ids)
            )
        )

    query = (
        resolve_db(None)
        .query(DocumentLocale)
        .filter(DocumentLocale.document_id == document_id)
    )
    if lang:
        query = query.filter(DocumentLocale.lang == lang)
    query.delete()


def _remove_archive_geometry(document_id):
    resolve_db(None).query(ArchiveDocumentGeometry).filter(
        ArchiveDocumentGeometry.document_id == document_id
    ).delete()


def _remove_geometry(document_id):
    resolve_db(None).query(DocumentGeometry).filter(
        DocumentGeometry.document_id == document_id
    ).delete()


def _remove_archive(archive_clazz, document_id):
    archive_document_ids = select(ArchiveDocument.id).where(
        ArchiveDocument.document_id == document_id
    )
    resolve_db(None).execute(
        archive_clazz.__table__.delete().where(
            getattr(archive_clazz, 'id').in_(archive_document_ids)
        )
    )
    resolve_db(None).query(ArchiveDocument).filter(
        ArchiveDocument.document_id == document_id
    ).delete()


def _remove_figures(clazz, document_id):
    resolve_db(None).query(clazz).filter(
        getattr(clazz, 'document_id') == document_id
    ).delete()


def _remove_document(document_id):
    resolve_db(None).query(Document).filter(
        Document.document_id == document_id
    ).delete()


def _remove_from_feed(document_id):
    resolve_db(None).query(DocumentChange).filter(
        DocumentChange.document_id == document_id
    ).delete()


def _remove_image_from_feed(document_id):
    items = (
        resolve_db(None)
        .query(DocumentChange)
        .filter(
            or_(
                DocumentChange.image1_id == document_id,
                DocumentChange.image2_id == document_id,
                DocumentChange.image3_id == document_id,
            )
        )
        .all()
    )
    for item in items:
        if (
            item.change_type == 'added_photos'
            and item.image1_id == document_id
            and not item.image2_id
        ):
            resolve_db(None).delete(item)
        else:
            if item.image1_id == document_id:
                item.image1_id = item.image2_id
                item.image2_id = item.image3_id
            elif item.image2_id == document_id:
                item.image2_id = item.image3_id
            item.image3_id = None
            item.more_images = False


def _remove_wp_from_routes_archives(document_id):
    resolve_db(None).query(ArchiveRoute).filter(
        ArchiveRoute.main_waypoint_id == document_id
    ).update({ArchiveRoute.main_waypoint_id: None})


def _remove_associations(document_id):
    resolve_db(None).query(Association).filter(
        or_(
            Association.parent_document_id == document_id,
            Association.child_document_id == document_id,
        )
    ).delete()
    resolve_db(None).query(AssociationLog).filter(
        or_(
            AssociationLog.parent_document_id == document_id,
            AssociationLog.child_document_id == document_id,
        )
    ).delete()
    resolve_db(None).query(TopoMapAssociation).filter(
        TopoMapAssociation.document_id == document_id
    ).delete()
    resolve_db(None).query(AreaAssociation).filter(
        AreaAssociation.document_id == document_id
    ).delete()


def _remove_tags(document_id):
    resolve_db(None).query(DocumentTag).filter(
        DocumentTag.document_id == document_id
    ).delete()
    resolve_db(None).query(DocumentTagLog).filter(
        DocumentTagLog.document_id == document_id
    ).delete()
