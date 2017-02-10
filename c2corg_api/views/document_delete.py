from c2corg_api.models import DBSession
from c2corg_api.models.article import ARTICLE_TYPE, Article, ArchiveArticle
from c2corg_api.models.association import Association
from c2corg_api.models.book import BOOK_TYPE, Book, ArchiveBook
from c2corg_api.models.cache_version import CacheVersion, \
    update_cache_version_full
from c2corg_api.models.document import (
    Document, DocumentLocale, ArchiveDocumentLocale,
    ArchiveDocument, DocumentGeometry, ArchiveDocumentGeometry)
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.es_sync import ESDeletedDocument
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE, Image, ArchiveImage
from c2corg_api.models.outing import (
    OUTING_TYPE, Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)
from c2corg_api.models.route import (
    ROUTE_TYPE, Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE, Waypoint, WaypointLocale, ArchiveWaypoint,
    ArchiveWaypointLocale)
from c2corg_api.models.xreport import (
    XREPORT_TYPE, Xreport, XreportLocale, ArchiveXreport,
    ArchiveXreportLocale)
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.image import delete_all_files_for_image
from c2corg_api.views.validation import validate_id
from cornice.resource import resource
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest
from sqlalchemy.sql.expression import or_, and_, exists
from sqlalchemy.sql.functions import func


def validate_document(request, **kwargs):
    if 'id' not in request.validated:
        return

    document_id = request.validated['id']
    document = DBSession.query(Document.type). \
        filter(Document.document_id == document_id).first()

    if not document:
        raise HTTPNotFound('document not found')

    document_type = document.type

    if document_type == WAYPOINT_TYPE:
        if _is_main_waypoint_of_route(document_id):
            raise HTTPBadRequest(
                'This waypoint cannot be deleted '
                'because it is a main waypoint.')

        if _is_only_waypoint_of_route(document_id):
            raise HTTPBadRequest(
                'This waypoint cannot be deleted because '
                'it is the only waypoint associated to some routes.')

    elif document_type == ROUTE_TYPE:
        if _is_only_route_of_outing(document_id):
            raise HTTPBadRequest(
                'This route cannot be deleted because '
                'it is the only route associated to some outings.')

    request.validated['document_type'] = document_type


def _is_main_waypoint_of_route(document_id):
    return DBSession.query(
        exists().
        where(Route.main_waypoint_id == document_id)
    ).scalar()


def _is_only_waypoint_of_route(document_id):
    routes = DBSession.query(Association.child_document_id). \
        filter(and_(
            Association.parent_document_id == document_id,
            Association.child_document_type == ROUTE_TYPE,
        )).subquery()
    only_waypoint = DBSession.query(Association). \
        filter(and_(
            Association.child_document_id == routes.c.child_document_id,
            Association.parent_document_type == WAYPOINT_TYPE
        )). \
        group_by(Association.child_document_id). \
        having(func.count('*') == 1). \
        exists()
    return DBSession.query(only_waypoint).scalar()


def _is_only_route_of_outing(document_id):
    outings = DBSession.query(Association.child_document_id). \
        filter(and_(
            Association.parent_document_id == document_id,
            Association.child_document_type == OUTING_TYPE,
        )).subquery()
    only_route = DBSession.query(Association). \
        filter(and_(
            Association.child_document_id == outings.c.child_document_id,
            Association.parent_document_type == ROUTE_TYPE
        )). \
        group_by(Association.child_document_id). \
        having(func.count('*') == 1). \
        exists()
    return DBSession.query(only_route).scalar()


@resource(path='/documents/delete/{id}', cors_policy=cors_policy)
class DeleteDocumentRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        validators=[validate_id, validate_document])
    def delete(self):
        """
        Delete a document.

        Request:
            `DELETE` `/documents/delete/{id}`
        """
        document_id = self.request.validated['id']
        document_type = self.request.validated['document_type']

        # Note: if an error occurs while deleting, SqlAlchemy will
        # automatically cancel all DB changes.

        _remove_from_cache(document_id)

        # Remove associations and update cache of formerly associated docs
        update_cache_version_full(document_id, document_type)
        _remove_associations(document_id)

        clazz, clazz_locale, archive_clazz, archive_clazz_locale = _get_models(
            document_type)

        # Order of removals depends on foreign key constraints
        _remove_history_metadata(document_id)
        _remove_archive_locale(archive_clazz_locale, document_id)
        _remove_archive_geometry(document_id)
        _remove_archive(archive_clazz, document_id)
        _remove_locale(clazz_locale, document_id)
        _remove_geometry(document_id)
        _remove_figures(clazz, document_id)
        _remove_from_feed(document_id)

        if document_type == IMAGE_TYPE:
            # Remove this image references from the feed
            _remove_image_from_feed(document_id)

        # When all references have been deleted, finally remove the main
        # document entry
        _remove_document(document_id)

        if document_type == IMAGE_TYPE:
            delete_all_files_for_image(document_id, self.request)

        _update_deleted_documents_list(document_id, document_type)
        notify_es_syncer(self.request.registry.queue_config)

        return {}


def _get_models(document_type):
    if document_type == WAYPOINT_TYPE:
        return Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale
    if document_type == ROUTE_TYPE:
        return Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale
    if document_type == OUTING_TYPE:
        return Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale
    if document_type == IMAGE_TYPE:
        return Image, None, ArchiveImage, None
    if document_type == ARTICLE_TYPE:
        return Article, None, ArchiveArticle, None
    if document_type == BOOK_TYPE:
        return Book, None, ArchiveBook, None
    if document_type == XREPORT_TYPE:
        return Xreport, XreportLocale, ArchiveXreport, ArchiveXreportLocale
    raise HTTPBadRequest('Unsupported type when deleting document')


def _remove_from_cache(document_id):
    DBSession.query(CacheVersion). \
        filter(CacheVersion.document_id == document_id).delete()


def _remove_history_metadata(document_id):
    history_metadata_ids = DBSession. \
        query(DocumentVersion.history_metadata_id). \
        filter(DocumentVersion.document_id == document_id). \
        all()
    DBSession.query(DocumentVersion). \
        filter(DocumentVersion.document_id == document_id). \
        delete()
    DBSession.execute(HistoryMetaData.__table__.delete().where(
        HistoryMetaData.id.in_(history_metadata_ids)
    ))


def _remove_archive_locale(archive_clazz_locale, document_id):
    if archive_clazz_locale:
        archive_document_locale_ids = DBSession. \
            query(ArchiveDocumentLocale.id). \
            filter(ArchiveDocumentLocale.document_id == document_id). \
            subquery()
        # FIXME document topic => to do with normal model instead?
        DBSession.execute(DocumentTopic.__table__.delete().where(
            DocumentTopic.document_locale_id.in_(
                archive_document_locale_ids)
        ))
        DBSession.execute(archive_clazz_locale.__table__.delete().where(
            getattr(archive_clazz_locale, 'id').in_(
                archive_document_locale_ids)
        ))

    DBSession.query(ArchiveDocumentLocale). \
        filter(ArchiveDocumentLocale.document_id == document_id). \
        delete()


def _remove_locale(clazz_locale, document_id):
    if clazz_locale:
        doc_locale_ids = DBSession.query(DocumentLocale.id). \
            filter(DocumentLocale.document_id == document_id). \
            subquery()
        DBSession.execute(clazz_locale.__table__.delete().where(
            getattr(clazz_locale, 'id').in_(doc_locale_ids)
        ))

    DBSession.query(DocumentLocale). \
        filter(DocumentLocale.document_id == document_id). \
        delete()


def _remove_archive_geometry(document_id):
    DBSession.query(ArchiveDocumentGeometry). \
        filter(ArchiveDocumentGeometry.document_id == document_id). \
        delete()


def _remove_geometry(document_id):
    DBSession.query(DocumentGeometry). \
        filter(DocumentGeometry.document_id == document_id). \
        delete()


def _remove_archive(archive_clazz, document_id):
    archive_document_ids = DBSession.query(ArchiveDocument.id). \
        filter(ArchiveDocument.document_id == document_id). \
        subquery()
    DBSession.execute(archive_clazz.__table__.delete().where(
        getattr(archive_clazz, 'id').in_(archive_document_ids)
    ))

    DBSession.query(ArchiveDocument). \
        filter(ArchiveDocument.document_id == document_id). \
        delete()


def _remove_figures(clazz, document_id):
    DBSession.query(clazz). \
        filter(getattr(clazz, 'document_id') == document_id). \
        delete()


def _remove_document(document_id):
    DBSession.query(Document). \
        filter(Document.document_id == document_id). \
        delete()


def _remove_from_feed(document_id):
    DBSession.query(DocumentChange). \
        filter(DocumentChange.document_id == document_id). \
        delete()


def _remove_image_from_feed(document_id):
    # TODO if removed doc is an image, it might be needed to remove
    # any reference to this image in feed items
    pass


def _remove_associations(document_id):
    DBSession.query(Association). \
        filter(or_(
            Association.parent_document_id == document_id,
            Association.child_document_id == document_id
        )).delete()


def _update_deleted_documents_list(document_id, document_type):
    DBSession.add(ESDeletedDocument(
        document_id=document_id, type=document_type))
