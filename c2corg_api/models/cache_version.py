import logging

from c2corg_api import caching
from c2corg_api.models import Base, schema, DBSession
from c2corg_api.models.document import Document
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import Integer, DateTime
from sqlalchemy import text

log = logging.getLogger(__name__)


class CacheVersion(Base):
    """This table contains a version number for each document that reflects
    the state of the document and all its associated documents.
    When the document or one of its associated documents is updated, the
    version of the document is incremented, so that outdated documents are not
    served from the cache.
    """
    __tablename__ = 'cache_versions'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        primary_key=True)

    document = relationship(
        Document, primaryjoin=document_id == Document.document_id
    )

    version = Column(Integer, nullable=False, server_default='1')
    last_updated = Column(
        DateTime(timezone=True), default=func.now(), server_default='now()',
        nullable=False)


def update_cache_version(document):
    update_cache_version_full(document.document_id, document.type)


def update_cache_version_full(document_id, type):
    """ Update the cache version of the given document + associated documents.
    """
    DBSession.execute(
        text('SELECT guidebook.update_cache_version(:document_id, :type)'),
        {'document_id': document_id, 'type': type}
    )


def update_cache_version_direct(document_id):
    """ Update the cache version for the document with the given id
    without updating any dependencies.
    """
    DBSession.execute(
        text('SELECT guidebook.increment_cache_version(:document_id)'),
        {'document_id': document_id}
    )


def update_cache_version_for_area(area):
    """ Invalidate the cache keys of all documents that are currently
    associated to the given area.
    Note that the cache key of the area itself is not changed when calling this
    function.
    """
    DBSession.execute(
        text('SELECT guidebook.update_cache_version_for_area(:document_id)'),
        {'document_id': area.document_id}
    )


def update_cache_version_for_map(topo_map):
    """ Invalidate the cache keys of all documents that are currently
    associated to the given map.
    Note that the cache key of the map itself is not changed when calling this
    function.
    """
    DBSession.execute(
        text('SELECT guidebook.update_cache_version_for_map(:document_id)'),
        {'document_id': topo_map.document_id}
    )


def update_cache_version_associations(
        added_associations, removed_associations, ignore_document_id=None):
    changed_associations = added_associations + removed_associations
    if not changed_associations:
        return

    documents_to_update = set()
    waypoints_to_update = set()
    routes_to_update = set()

    for association in changed_associations:
        documents_to_update.add(association['parent_id'])
        documents_to_update.add(association['child_id'])

        if association['parent_type'] == WAYPOINT_TYPE and \
                association['child_type'] == ROUTE_TYPE:
            waypoints_to_update.add(association['parent_id'])
        elif association['parent_type'] == ROUTE_TYPE and \
                association['child_type'] == OUTING_TYPE:
            routes_to_update.add(association['parent_id'])

    if ignore_document_id is not None:
        documents_to_update.remove(ignore_document_id)

    if documents_to_update:
        # update the cache version of the documents of added and removed
        # associations
        DBSession.execute(
            text('SELECT guidebook.increment_cache_versions(:document_ids)'),
            {'document_ids': list(documents_to_update)}
        )

    if waypoints_to_update:
        # if an association between waypoint and route was removed/added,
        # the waypoint parents and grand-parents have to be updated
        DBSession.execute(
            text('SELECT guidebook.update_cache_version_of_waypoints(:waypoint_ids)'),  # noqa: E501
            {'waypoint_ids': list(waypoints_to_update)}
        )

    if routes_to_update:
        # if an association between route and outing was removed/added,
        # waypoints (and parents and grand-parents) associated to the route
        # have to be updated
        DBSession.execute(
            text('SELECT guidebook.update_cache_version_of_routes(:route_ids)'),  # noqa: E501
            {'route_ids': list(routes_to_update)}
        )


def _format_cache_key(document_id, lang, version, doc_type=None,
                      custom_cache_key=None):
    if not version:
        # no version for this document id, the document should not exist
        log.debug('no version for document id {0}'.format(document_id))
        return None

    cache_key = None
    if not lang:
        cache_key = '{0}-{1}-{2}'.format(
            document_id, version, caching.CACHE_VERSION)
    else:
        cache_key = '{0}-{1}-{2}-{3}'.format(
            document_id, lang, version, caching.CACHE_VERSION)

    if doc_type:
        cache_key = '{0}-{1}'.format(cache_key, doc_type)

    # custom_cache_key is used for xreports to distinguish between the cache
    # values for users that are allowed to see the full xreport with personal
    # data (moderators and the creator of the xreport) and a public version for
    # all other users.
    if custom_cache_key:
        cache_key = '{0}-{1}'.format(cache_key, custom_cache_key)

    return cache_key


def get_cache_key(document_id, lang, document_type,
                  custom_cache_key=None):
    """ Returns an identifier which reflects the version of a document and
    all its associated documents. This identifier is used as cache key
    and as ETag value.
    """
    version = DBSession.query(CacheVersion.version). \
        filter(CacheVersion.document_id == document_id). \
        first()

    return _format_cache_key(
        document_id, lang, version[0] if version else None, document_type,
        custom_cache_key)


def get_cache_keys(document_ids, lang, document_type):
    """ Get a cache key for all given document ids.
    """
    if not document_ids:
        return []

    versions = DBSession.query(CacheVersion). \
        filter(CacheVersion.document_id.in_(document_ids)). \
        join(Document,
             Document.document_id == CacheVersion.document_id). \
        filter(Document.redirects_to.is_(None)). \
        all()
    version_for_documents = {v.document_id: v.version for v in versions}

    return [
        _format_cache_key(
            document_id,
            lang,
            version_for_documents.get(document_id),
            document_type
        ) for document_id in document_ids
        if version_for_documents.get(document_id)
    ]


def get_document_id(cache_key):
    return int(cache_key.split('-')[0])

def get_version_date(document_id, version):
 
    date = DBSession.query(CacheVersion.last_updated). \
        filter(CacheVersion.document_id == document_id and CacheVersion.version == version ). \
        first()
    return date