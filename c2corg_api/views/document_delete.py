from c2corg_api.models import DBSession, article, image
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import ARTICLE_TYPE, Article, ArchiveArticle
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import BOOK_TYPE, Book, ArchiveBook
from c2corg_api.models.cache_version import CacheVersion, \
    update_cache_version_full
from c2corg_api.models.document import (
    Document, DocumentLocale, ArchiveDocumentLocale,
    ArchiveDocument, DocumentGeometry, ArchiveDocumentGeometry,
    get_available_langs)
from c2corg_api.models.document_history import HistoryMetaData, \
    DocumentVersion, has_been_created_by, is_less_than_24h_old
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.feed import DocumentChange, update_langs_of_changes
from c2corg_api.models.image import IMAGE_TYPE, Image, ArchiveImage
from c2corg_api.models.outing import (
    OUTING_TYPE, Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)
from c2corg_api.models.route import (
    ROUTE_TYPE, Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE, Waypoint, WaypointLocale, ArchiveWaypoint,
    ArchiveWaypointLocale)
from c2corg_api.models.xreport import (
    XREPORT_TYPE, Xreport, XreportLocale, ArchiveXreport,
    ArchiveXreportLocale)
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.image import delete_all_files_for_image
from c2corg_api.views.validation import validate_id, validate_lang
from cornice.resource import resource
from sqlalchemy.sql.expression import or_, and_, exists, over
from sqlalchemy.sql.functions import func


def validate_document_type(request, **kwargs):
    if 'id' not in request.validated:
        return

    document_id = request.validated['id']
    document = DBSession.query(Document.type). \
        filter(Document.document_id == document_id).first()

    if not document:
        request.errors.add(
            'querystring',
            'document_id',
            'document not found')
        request.errors.status = 404
        return

    document_type = document.type
    if document_type not in (WAYPOINT_TYPE,
                             ROUTE_TYPE,
                             OUTING_TYPE,
                             IMAGE_TYPE,
                             ARTICLE_TYPE,
                             BOOK_TYPE,
                             XREPORT_TYPE):
        request.errors.add(
            'querystring',
            'document_id',
            'Unsupported type when deleting document')
        return
    request.validated['document_type'] = document_type


def validate_document(request, **kwargs):
    if 'id' not in request.validated or \
            'document_type' not in request.validated:
        return

    document_id = request.validated['id']
    document_type = request.validated['document_type']

    if 'lang' in request.validated:
        # Tests specific to a locale-only deletion
        lang = request.validated['lang']
        available_langs = get_available_langs(document_id)
        if lang not in available_langs:
            request.errors.add(
                'querystring',
                'lang',
                'locale not found')
            return
        request.validated['is_only_locale'] = len(available_langs) == 1
        if not request.validated['is_only_locale']:
            # When there are other locales left, the whole document is not
            # deleted. Following tests are then not required.
            request.validated['document_type'] = document_type
            return

    if document_type == WAYPOINT_TYPE:
        if _is_main_waypoint_of_route(document_id):
            request.errors.add(
                'querystring',
                'document_id',
                'This waypoint cannot be deleted '
                'because it is a main waypoint.')
            return

        if _is_only_waypoint_of_route(document_id):
            request.errors.add(
                'querystring',
                'document_id',
                'This waypoint cannot be deleted because '
                'it is the only waypoint associated to some routes.')
            return

    elif document_type == ROUTE_TYPE:
        if _is_only_route_of_outing(document_id):
            request.errors.add(
                'querystring',
                'document_id',
                'This route cannot be deleted because '
                'it is the only route associated to some outings.')
            return


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


def validate_requestor(request, **kwargs):
    if request.has_permission('moderator'):
        return

    if 'id' not in request.validated or \
            'document_type' not in request.validated:
        return

    document_id = request.validated['id']
    document_type = request.validated['document_type']

    # Only personal documents might be deleted
    if document_type in (WAYPOINT_TYPE, ROUTE_TYPE, BOOK_TYPE):
        request.errors.add(
            'querystring',
            'document_type',
            'No permission to delete this document')
        return

    if not is_less_than_24h_old(document_id):
        request.errors.add(
            'querystring',
            'document_id',
            'Only document less than 24h old can be deleted')
        return

    user_id = request.authenticated_userid

    if document_type == OUTING_TYPE or document_type == XREPORT_TYPE:
        if not has_been_created_by(document_id, user_id):
            request.errors.add(
                'querystring',
                'document_id',
                'Only the initial author can delete this document')
        return

    if ((document_type == IMAGE_TYPE and image.is_personal(document_id)) or
        (document_type == ARTICLE_TYPE and article.is_personal(document_id))) \
            and has_been_created_by(document_id, user_id):
        # Deletion is legal
        return

    request.errors.add(
        'querystring',
        'document_id',
        'No permission to delete this document')


class DeleteBase(object):

    def __init__(self, request):
        self.request = request

    def _delete(self, document_id, document_type):
        if document_type == IMAGE_TYPE:
            # Files are actually removed only if the transaction succeeds
            delete_all_files_for_image(document_id, self.request)

        self._delete_document(document_id, document_type)

        update_deleted_documents_list(document_id, document_type)
        notify_es_syncer(self.request.registry.queue_config)

        return {}

    def _delete_document(self, document_id, document_type, redirecting=False):
        # Check if documents are redirecting (merged) to the document to delete
        # If yes, delete them first.
        self._remove_merged_documents(document_id, document_type)

        remove_from_cache(document_id)

        # Remove associations and update cache of formerly associated docs
        update_cache_version_full(document_id, document_type)
        _remove_associations(document_id)
        _remove_tags(document_id)

        clazz, clazz_locale, archive_clazz, archive_clazz_locale = _get_models(
            document_type)

        if not redirecting:
            _remove_from_feed(document_id)

        if not redirecting and document_type == IMAGE_TYPE:
            # Remove the references of this image from the feed
            _remove_image_from_feed(document_id)

        if document_type == WAYPOINT_TYPE:
            _remove_waypoint_from_routes_archives_main_waypoint_id(document_id)
        remove_whole_document(document_id, clazz, clazz_locale,
                              archive_clazz, archive_clazz_locale)

    def _remove_merged_documents(self, document_id, document_type):
        merged_document_ids = DBSession.query(ArchiveDocument.document_id). \
            filter(ArchiveDocument.redirects_to == document_id).all()
        for merged_document_id in merged_document_ids:
            self._delete_document(merged_document_id, document_type, True)


@resource(path='/documents/delete/{id}', cors_policy=cors_policy)
class DeleteDocumentRest(DeleteBase):

    @restricted_json_view(
        permission='authenticated',
        validators=[validate_id, validate_document_type, validate_requestor,
                    validate_document])
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

        return self._delete(document_id, document_type)


@resource(path='/documents/delete/{id}/{lang}', cors_policy=cors_policy)
class DeleteDocumentLocaleRest(DeleteBase):

    @restricted_json_view(
        permission='moderator',
        validators=[validate_id, validate_lang, validate_document_type,
                    validate_document])
    def delete(self):
        """
        Delete a document locale.

        Request:
            `DELETE` `/documents/delete/{id}/{lang}`
        """
        document_id = self.request.validated['id']
        document_type = self.request.validated['document_type']
        lang = self.request.validated['lang']

        # Note: if an error occurs while deleting, SqlAlchemy will
        # automatically cancel all DB changes.

        # If only one locale is available, deleting it implies to remove
        # the whole document.
        if self.request.validated['is_only_locale']:
            return self._delete(document_id, document_type)

        clazz, clazz_locale, archive_clazz, archive_clazz_locale = _get_models(
            document_type)

        _remove_locale_versions(document_id, lang)
        _remove_archive_locale(archive_clazz_locale, document_id, lang)
        _remove_locale(clazz_locale, document_id, lang)
        update_langs_of_changes(document_id)

        update_cache_version_full(document_id, document_type)

        update_deleted_locales_list(document_id, document_type, lang)
        notify_es_syncer(self.request.registry.queue_config)

        return {}


def remove_whole_document(document_id, clazz, clazz_locale,
                          archive_clazz, archive_clazz_locale):
    # Order of removals depends on foreign key constraints
    _remove_versions(document_id)
    _remove_archive_locale(archive_clazz_locale, document_id)
    _remove_archive_geometry(document_id)
    _remove_archive(archive_clazz, document_id)
    _remove_locale(clazz_locale, document_id)
    _remove_geometry(document_id)
    _remove_figures(clazz, document_id)
    # When all references have been deleted, finally remove the main
    # document entry:
    _remove_document(document_id)


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
    assert False


def remove_from_cache(document_id):
    DBSession.query(CacheVersion). \
        filter(CacheVersion.document_id == document_id).delete()


def _remove_versions(document_id):
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


def _remove_locale_versions(document_id, lang):
    # Only history metadata not shared with other locales should be removed.
    # This subquery gets the list of history_metadata_id with their lang and
    # number of associated locales:
    t = DBSession.query(
        DocumentVersion.history_metadata_id,
        DocumentVersion.lang,
        over(
            func.count('*'),
            partition_by=DocumentVersion.history_metadata_id).label('cnt')). \
        filter(DocumentVersion.document_id == document_id). \
        subquery('t')
    # Gets the list of history_metadata_id associated only
    # to the current locale:
    history_metadata_ids = DBSession.query(t.c.history_metadata_id). \
        filter(t.c.lang == lang).filter(t.c.cnt == 1).all()

    DBSession.query(DocumentVersion). \
        filter(DocumentVersion.document_id == document_id). \
        filter(DocumentVersion.lang == lang).delete()

    if len(history_metadata_ids):
        DBSession.execute(HistoryMetaData.__table__.delete().where(
            HistoryMetaData.id.in_(history_metadata_ids)
        ))


def _remove_archive_locale(archive_clazz_locale, document_id, lang=None):
    if archive_clazz_locale:
        query = DBSession.query(ArchiveDocumentLocale.id). \
            filter(ArchiveDocumentLocale.document_id == document_id)
        if lang:
            query = query.filter(ArchiveDocumentLocale.lang == lang)
        archive_document_locale_ids = query.subquery()
        DBSession.execute(archive_clazz_locale.__table__.delete().where(
            getattr(archive_clazz_locale, 'id').in_(
                archive_document_locale_ids)
        ))

    query = DBSession.query(ArchiveDocumentLocale). \
        filter(ArchiveDocumentLocale.document_id == document_id)
    if lang:
        query = query.filter(ArchiveDocumentLocale.lang == lang)
    query.delete()


def _remove_locale(clazz_locale, document_id, lang=None):
    query = DBSession.query(DocumentLocale.id). \
        filter(DocumentLocale.document_id == document_id)
    if lang:
        query = query.filter(DocumentLocale.lang == lang)
    document_locale_ids = query.subquery()
    # Remove links to comments (comments themselves are not removed)
    DBSession.execute(DocumentTopic.__table__.delete().where(
        DocumentTopic.document_locale_id.in_(document_locale_ids)
    ))

    if clazz_locale:
        DBSession.execute(clazz_locale.__table__.delete().where(
            getattr(clazz_locale, 'id').in_(document_locale_ids)
        ))

    query = DBSession.query(DocumentLocale). \
        filter(DocumentLocale.document_id == document_id)
    if lang:
        query = query.filter(DocumentLocale.lang == lang)
    query.delete()


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
    # If removed doc is an image, it might be needed to remove
    # any reference to this image in feed items
    items = DBSession.query(DocumentChange). \
        filter(or_(
            DocumentChange.image1_id == document_id,
            DocumentChange.image2_id == document_id,
            DocumentChange.image3_id == document_id
        )).all()
    for item in items:
        if item.change_type == 'added_photos' and \
                item.image1_id == document_id and \
                not item.image2_id:
            # Remove feed item if no other image was added
            DBSession.delete(item)
        else:
            # Shift image references in the feed item
            if item.image1_id == document_id:
                item.image1_id = item.image2_id
                item.image2_id = item.image3_id
            elif item.image2_id == document_id:
                item.image2_id = item.image3_id
            item.image3_id = None
            item.more_images = False


def _remove_waypoint_from_routes_archives_main_waypoint_id(document_id):
    DBSession.query(ArchiveRoute). \
        filter(ArchiveRoute.main_waypoint_id == document_id). \
        update({ArchiveRoute.main_waypoint_id: None})


def _remove_associations(document_id):
    DBSession.query(Association). \
        filter(or_(
            Association.parent_document_id == document_id,
            Association.child_document_id == document_id
        )).delete()
    DBSession.query(AssociationLog). \
        filter(or_(
            AssociationLog.parent_document_id == document_id,
            AssociationLog.child_document_id == document_id
        )).delete()
    DBSession.query(TopoMapAssociation). \
        filter(TopoMapAssociation.document_id == document_id).delete()
    DBSession.query(AreaAssociation). \
        filter(AreaAssociation.document_id == document_id).delete()


def _remove_tags(document_id):
    DBSession.query(DocumentTag). \
        filter(DocumentTag.document_id == document_id).delete()
    DBSession.query(DocumentTagLog). \
        filter(DocumentTagLog.document_id == document_id).delete()


def update_deleted_documents_list(document_id, document_type):
    DBSession.add(ESDeletedDocument(
        document_id=document_id, type=document_type))


def update_deleted_locales_list(document_id, document_type, lang):
    DBSession.add(ESDeletedLocale(
        document_id=document_id, type=document_type, lang=lang))
