import logging

from c2corg_api import DBSession
from c2corg_api.models.area import AREA_TYPE, Area, ArchiveArea
from c2corg_api.models.area_association import update_areas_for_document
from c2corg_api.models.article import ARTICLE_TYPE, Article, ArchiveArticle
from c2corg_api.models.book import BOOK_TYPE, Book, ArchiveBook
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.document import (
    Document, DocumentLocale, ArchiveDocumentLocale, UpdateType)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.feed import update_feed_document_update
from c2corg_api.models.image import IMAGE_TYPE, Image, ArchiveImage
from c2corg_api.models.outing import (
    OUTING_TYPE, Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)
from c2corg_api.models.route import (
    ROUTE_TYPE, Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.topo_map_association import update_maps_for_document
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE, Waypoint, WaypointLocale, ArchiveWaypoint,
    ArchiveWaypointLocale)
from c2corg_api.models.xreport import (
    XREPORT_TYPE, Xreport, XreportLocale, ArchiveXreport, ArchiveXreportLocale)
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.area import update_associations
from c2corg_api.views.document import DocumentRest
from c2corg_api.views.waypoint import update_linked_route_titles
from c2corg_api.views.route import update_title_prefix
from c2corg_common.attributes import default_langs
from colander import (
    MappingSchema, SchemaNode, Integer, String, required, OneOf)
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest, HTTPConflict
from sqlalchemy.orm import joinedload, contains_eager
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm.util import with_polymorphic
from sqlalchemy.sql.expression import exists, and_

log = logging.getLogger(__name__)


class RevertSchema(MappingSchema):
    document_id = SchemaNode(Integer(), missing=required)
    lang = SchemaNode(String(), missing=required,
                      validator=OneOf(default_langs))
    version_id = SchemaNode(Integer(), missing=required)


def validate_version(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']
    version_id = request.validated['version_id']

    # check the version to revert to actually exists
    version_exists = DBSession.query(
        exists().where(
            and_(DocumentVersion.id == version_id,
                 DocumentVersion.document_id == document_id,
                 DocumentVersion.lang == lang))
    ).scalar()
    if not version_exists:
        raise HTTPBadRequest('Unknown version {}/{}/{}'.format(
            document_id, lang, version_id))

    # check the version to revert to is not the latest one
    last_version_id, = DBSession.query(DocumentVersion.id). \
        filter(and_(
            DocumentVersion.document_id == document_id,
            DocumentVersion.lang == lang)). \
        order_by(DocumentVersion.id.desc()).first()
    if version_id == last_version_id:
        raise HTTPBadRequest(
            'Version {}/{}/{} is already the latest one'.format(
                document_id, lang, version_id))


@resource(path='/documents/revert', cors_policy=cors_policy)
class DocumentRevertRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=RevertSchema(),
        validators=[colander_body_validator, validate_version])
    def post(self):
        """ Create a new version of the document based upon an old one.

        Request:
            `POST` `/documents/revert`

        Request body:
            {
                'document_id': @document_id@,
                'lang': @lang@,
                'version_id': @version_id@
            }

        """
        document_id = self.request.validated['document_id']
        lang = self.request.validated['lang']
        version_id = self.request.validated['version_id']

        clazz, locale_clazz, archive_clazz, \
            archive_locale_clazz, document_type = self._get_models(document_id)

        document = self._get_current_document(
            document_id, lang, clazz, locale_clazz)
        document_in = self._get_archive_document(
            document_id, lang, version_id, archive_clazz, archive_locale_clazz)

        old_versions = document.get_versions()
        user_id = self.request.authenticated_userid

        # update the document with the input document
        document.update(document_in)

        # now set back the versions to the versions of the current document
        # because we are basing our changes on the lastest version
        document.version = old_versions['document']
        document.locales[0].version = old_versions['locales'][lang]
        if document.geometry:
            document.geometry.version = old_versions['geometry']

        # 'before_update' callbacks as in _put() are generally not required
        # when reverting, except maybe if associated WP/routes have changed.
        # See 'after_update' handling below

        try:
            DBSession.flush()
        except StaleDataError:
            raise HTTPConflict('concurrent modification')

        # when flushing the session, SQLAlchemy automatically updates the
        # version numbers in case attributes have changed. by comparing with
        # the old version numbers, we can check if only figures or only locales
        # have changed.
        (update_types, changed_langs) = document.get_update_type(old_versions)

        if update_types:
            # A new version needs to be created and persisted
            message = 'Revert to version {}'.format(version_id)
            DocumentRest.update_version(
                document, user_id, message, update_types, changed_langs)

            if document.type != AREA_TYPE and UpdateType.GEOM in update_types:
                update_areas_for_document(document, reset=True)

            if document.type != MAP_TYPE and UpdateType.GEOM in update_types:
                update_maps_for_document(document, reset=True)

            after_update = self._get_after_update(document_type)
            if after_update:
                after_update(document, update_types, user_id=user_id)

            update_cache_version(document)
            # update search index
            notify_es_syncer(self.request.registry.queue_config)
            update_feed_document_update(document, user_id, update_types)
        else:
            raise HTTPBadRequest(
                'No change to apply when reverting to this version')

        return {}

    def _get_models(self, document_id):
        document_type, = DBSession.query(Document.type). \
            filter(Document.document_id == document_id).first()

        if document_type == WAYPOINT_TYPE:
            return Waypoint, WaypointLocale, ArchiveWaypoint, \
                   ArchiveWaypointLocale, document_type
        if document_type == ROUTE_TYPE:
            return Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale, \
                   document_type
        if document_type == OUTING_TYPE:
            return Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale, \
                   document_type
        if document_type == IMAGE_TYPE:
            return Image, None, ArchiveImage, ArchiveDocumentLocale, \
                   document_type
        if document_type == ARTICLE_TYPE:
            return Article, None, ArchiveArticle, ArchiveDocumentLocale, \
                   document_type
        if document_type == BOOK_TYPE:
            return Book, None, ArchiveBook, ArchiveDocumentLocale, \
                   document_type
        if document_type == XREPORT_TYPE:
            return Xreport, XreportLocale, ArchiveXreport, \
                   ArchiveXreportLocale, document_type
        if document_type == AREA_TYPE:
            return Area, None, ArchiveArea, ArchiveDocumentLocale, \
                   document_type
        assert False

    def _get_archive_document(self, document_id, lang, version_id,
                              archive_clazz, archive_locale_clazz):
        version = DBSession.query(DocumentVersion) \
            .options(joinedload(
                DocumentVersion.document_archive.of_type(archive_clazz))) \
            .options(joinedload(
                DocumentVersion.document_locales_archive.of_type(
                    archive_locale_clazz))) \
            .options(joinedload(DocumentVersion.document_geometry_archive)) \
            .filter(DocumentVersion.id == version_id) \
            .filter(DocumentVersion.document_id == document_id) \
            .filter(DocumentVersion.lang == lang) \
            .first()

        archive_document = version.document_archive
        archive_document.geometry = version.document_geometry_archive
        archive_document.locales = [version.document_locales_archive]
        return archive_document

    def _get_current_document(self, document_id, lang, clazz, clazz_locale):
        locales_type = with_polymorphic(DocumentLocale, clazz_locale) \
            if clazz_locale else DocumentLocale
        locales_attr = getattr(clazz, 'locales')
        locales_type_eager = locales_attr.of_type(clazz_locale) \
            if clazz_locale else locales_attr

        document_query = DBSession. \
            query(clazz). \
            join(locales_type). \
            filter(getattr(clazz, 'document_id') == document_id). \
            filter(DocumentLocale.lang == lang). \
            options(joinedload('geometry')). \
            options(contains_eager(locales_type_eager, alias=locales_type))
        return document_query.first()

    def _get_after_update(self, document_type):
        if document_type == WAYPOINT_TYPE:
            return update_linked_route_titles
        if document_type == ROUTE_TYPE:
            return update_title_prefix
        if document_type == AREA_TYPE:
            return update_associations
        return None
