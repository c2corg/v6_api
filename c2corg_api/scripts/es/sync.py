from c2corg_api.models import es_sync, document_types, document_locale_types
from c2corg_api.models.area import Area
from c2corg_api.models.association import AssociationLog, Association
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.document_tag import DocumentTagLog
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.outing import Outing, OUTING_TYPE
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.utils import windowed_query
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.views.document_listings import add_load_for_profiles
from sqlalchemy.orm import joinedload
import logging

from sqlalchemy.sql.elements import literal
from sqlalchemy.sql.expression import or_, and_, union

log = logging.getLogger(__name__)


def sync_es(session, batch_size=1000):
    last_update, date_now = es_sync.get_status(session)
    log.info('Last update time: {}'.format(last_update))

    if not last_update:
        raise Exception('No last update time, run `fill_index` to do an '
                        'initial import into ElasticSearch')

    # get all documents that have changed since the last update
    changed_documents = \
        get_changed_documents(session, last_update) + \
        get_changed_users(session, last_update) + \
        get_changed_documents_for_associations(session, last_update) + \
        get_deleted_locale_documents(session, last_update) + \
        get_tagged_documents(session, last_update)
    log.info('Number of changed documents: {}'.format(len(changed_documents)))
    if changed_documents:
        sync_documents(session, changed_documents, batch_size)

    # get list of documents deleted since the last update
    deleted_documents = get_deleted_documents(session, last_update)
    log.info('Number of deleted documents: {}'.format(len(deleted_documents)))
    if deleted_documents:
        sync_deleted_documents(session, deleted_documents, batch_size)

    es_sync.mark_as_updated(session, date_now)
    log.info('Sync has finished')


def get_changed_documents(session, last_update):
    """Get the documents that have changed since the last update.
    Returns a list of (document_id, document_type) tuples ordered by
    document_type.
    """
    # TODO if there are many changed documents getting all ids is not very
    # efficient. stop in that case and prompt to run `fill_index` manually?
    return session.query(Document.document_id, Document.type). \
        join(DocumentVersion,
             Document.document_id == DocumentVersion.document_id). \
        join(HistoryMetaData,
             HistoryMetaData.id ==
             DocumentVersion.history_metadata_id). \
        filter(HistoryMetaData.written_at >= last_update). \
        group_by(Document.document_id, Document.type). \
        order_by(Document.type). \
        all()


def get_changed_users(session, last_update):
    """Get the users that have changed. Needed to update the profile when
    the user name has changed.
    """
    return session.query(User.id, literal(USERPROFILE_TYPE)). \
        filter(User.last_modified >= last_update). \
        all()


def get_changed_documents_for_associations(session, last_update):
    """ Check if associations have been created/removed. If so return the
    documents that have to be updated.
    """
    associations_changed = session.query(AssociationLog). \
        filter(or_(*[
            and_(
                AssociationLog.parent_document_type == parent_type,
                AssociationLog.child_document_type == child_type
            ) for (parent_type, child_type) in association_types_to_check
        ])). \
        filter(AssociationLog.written_at >= last_update). \
        exists()

    if not session.query(associations_changed).scalar():
        return []

    return get_changed_routes_from_associations(session, last_update)


def get_changed_routes_from_associations(session, last_update):
    return \
        get_changed_routes_wr(session, last_update) + \
        get_changed_routes_and_outings_ww(session, last_update) + \
        get_changed_outings_ro_uo(session, last_update)


def get_changed_routes_wr(session, last_update):
    """ Returns the routes when associations between waypoint and route have
    been created/removed.

    E.g. when an association between waypoint W1 and route R1 is created,
    route R1 has to be updated so that W1 is listed under
    `associated_waypoints_ids`.
    """
    return session. \
        query(AssociationLog.child_document_id, literal(ROUTE_TYPE)). \
        filter(and_(
            AssociationLog.parent_document_type == WAYPOINT_TYPE,
            AssociationLog.child_document_type == ROUTE_TYPE
        )). \
        filter(AssociationLog.written_at >= last_update). \
        all()


def get_changed_routes_and_outings_ww(session, last_update):
    """ Returns the routes and outings when associations between waypoint
    and waypoint have been created/removed.
    E.g. when an association between waypoint W1 and W2 is created,
    all routes associated to W2, all routes associated to the direct
    children of W2 and all outings associated to these routes have to be
    updated.

    For example given the following associations:
    W1 -> W2, W2 -> W3, W3 -> R1
    Route R1 has the following `associated_waypoint_ids`: W3, W2, W1

    When association W1 -> W2 is deleted, all routes linked to W2 and all
    routes linked to the direct waypoint children of W2 (in this case W3) have
    to be updated.
    After the update, `associated_waypoint_ids` of R1 is: W3, W2
    """
    select_changed_waypoints = session. \
        query(AssociationLog.child_document_id.label('waypoint_id')). \
        filter(and_(
            AssociationLog.parent_document_type == WAYPOINT_TYPE,
            AssociationLog.child_document_type == WAYPOINT_TYPE
        )). \
        filter(AssociationLog.written_at >= last_update). \
        cte('changed_waypoints')
    select_changed_waypoint_children = session. \
        query(Association.child_document_id.label('waypoint_id')). \
        select_from(select_changed_waypoints). \
        join(
            Association,
            and_(
                Association.parent_document_id ==
                select_changed_waypoints.c.waypoint_id,
                Association.child_document_type == WAYPOINT_TYPE
            )). \
        cte('changed_waypoint_children')

    select_all_changed_waypoints = union(
        select_changed_waypoints.select(),
        select_changed_waypoint_children.select()). \
        cte('all_changed_waypoints')

    select_changed_routes = session. \
        query(
            Association.child_document_id.label('route_id')
            ). \
        select_from(select_all_changed_waypoints). \
        join(
            Association,
            and_(
                Association.parent_document_id ==
                select_all_changed_waypoints.c.waypoint_id,
                Association.child_document_type == ROUTE_TYPE
            )). \
        group_by(Association.child_document_id). \
        cte('changed_routes')

    select_changed_outings = session. \
        query(
            Association.child_document_id.label('outing_id')). \
        select_from(select_changed_routes). \
        join(
            Association,
            and_(
                Association.parent_document_id ==
                select_changed_routes.c.route_id,
                Association.child_document_type == OUTING_TYPE
            )). \
        group_by(Association.child_document_id). \
        cte('changed_outings')

    select_changed_routes_and_outings = union(
        session.query(
            select_changed_routes.c.route_id.label('document_id'),
            literal(ROUTE_TYPE).label('type')
        ).select_from(select_changed_routes),
        session.query(
            select_changed_outings.c.outing_id.label('document_id'),
            literal(OUTING_TYPE).label('type')
        ).select_from(select_changed_outings)). \
        cte('changed_routes_and_outings')

    return session. \
        query(
            select_changed_routes_and_outings.c.document_id,
            select_changed_routes_and_outings.c.type). \
        select_from(select_changed_routes_and_outings). \
        all()


def get_changed_outings_ro_uo(session, last_update):
    """ Returns the outings when associations between outing and route, or
    between outing and user have been created/removed.

    E.g. when an association between outing O1 and route R1 is created,
    outing O1 has to be updated so that all waypoints associated to R1 are
    listed under `associated_waypoints_ids`, and so that R1 is listed under
    `associated_routes_ids`.
    """
    return session. \
        query(
            AssociationLog.child_document_id.label('outing_id'),
            literal(OUTING_TYPE).label('type')). \
        filter(or_(
            and_(
                AssociationLog.parent_document_type == ROUTE_TYPE,
                AssociationLog.child_document_type == OUTING_TYPE
            ),
            and_(
                AssociationLog.parent_document_type == USERPROFILE_TYPE,
                AssociationLog.child_document_type == OUTING_TYPE
            )
        )). \
        filter(AssociationLog.written_at >= last_update). \
        group_by('outing_id', 'type'). \
        all()


def get_deleted_locale_documents(session, last_update):
    """Returns the ids of documents that had locales deleted
    since the last update.
    """
    return session. \
        query(ESDeletedLocale.document_id, ESDeletedLocale.type) . \
        filter(ESDeletedLocale.deleted_at >= last_update). \
        group_by(ESDeletedLocale.document_id, ESDeletedLocale.type). \
        all()


def get_deleted_documents(session, last_update):
    """Returns the ids of documents deleted since the last update.
    """
    return session. \
        query(ESDeletedDocument.document_id, ESDeletedDocument.type) . \
        filter(ESDeletedDocument.deleted_at >= last_update). \
        all()


def get_tagged_documents(session, last_update):
    """Returns the ids of documents tagged/untagged since the last update.
    """
    return session. \
        query(DocumentTagLog.document_id, DocumentTagLog.document_type). \
        filter(DocumentTagLog.written_at >= last_update). \
        all()


def sync_documents(session, changed_documents, batch_size):
    client = elasticsearch_config['client']
    batch = ElasticBatch(client, batch_size)
    with batch:
        docs_per_type = get_documents_per_type(changed_documents)
        add_dependent_documents(session, docs_per_type)
        for doc_type, document_ids in docs_per_type.items():
            if document_ids:
                docs = get_documents(
                    session, doc_type, batch_size, document_ids)
                create_search_documents(doc_type, docs, batch)


def sync_deleted_documents(session, deleted_documents, batch_size):
    client = elasticsearch_config['client']
    batch = ElasticBatch(client, batch_size)
    index = elasticsearch_config['index']
    n = 0
    with batch:
        for document_id, doc_type in deleted_documents:
            batch.add({
                '_index': index,
                '_id': document_id,
                '_type': doc_type,
                'id': document_id,
                '_op_type': 'delete'
            })
            n += 1
    log.info('Removed {} document(s)'.format(n))


def add_dependent_documents(session, docs_per_type):
    add_routes_for_waypoints(session, docs_per_type)


def add_routes_for_waypoints(session, docs_per_type):
    """Add the routes that have one of the waypoints as main waypoints.
    """
    changed_waypoint_ids = docs_per_type.get(WAYPOINT_TYPE, [])
    if not changed_waypoint_ids:
        return

    linked_route_ids = session.query(Route.document_id). \
        filter(Route.main_waypoint_id.in_(changed_waypoint_ids)).all()

    route_ids = docs_per_type.setdefault(ROUTE_TYPE, set())
    route_ids.update(linked_route_ids)


def get_documents_per_type(changed_documents):
    docs_per_type = {}
    for document_id, doc_type in changed_documents:
        docs = docs_per_type.setdefault(doc_type, set())
        docs.add(document_id)
    return docs_per_type


def get_documents(session, doc_type, batch_size, document_ids=None,
                  ignore_redirects=False):
    clazz = document_types[doc_type]
    locales_clazz = document_locale_types[doc_type]

    base_query = session.query(clazz)
    if ignore_redirects:
        base_query = base_query.filter(clazz.redirects_to.is_(None))
    if document_ids:
        base_query = base_query.filter(clazz.document_id.in_(document_ids))

    locale_fields = ['title']
    if clazz == Route:
        locale_fields.append('title_prefix')

    base_query = base_query. \
        options(joinedload(clazz.locales.of_type(locales_clazz)).
                load_only(*locale_fields)). \
        options(joinedload(clazz.geometry).load_only(DocumentGeometry.lon_lat))

    if clazz != Area:
        base_query = base_query. \
            options(joinedload(clazz._areas).load_only('document_id'))

    if clazz == Route:
        base_query = base_query. \
            options(
                joinedload(Route.associated_waypoints_ids).
                load_only('waypoint_ids'))

    if clazz == Outing:
        base_query = base_query. \
            options(
                joinedload(Outing.associated_waypoints_ids).
                load_only('waypoint_ids'))

    base_query = add_load_for_profiles(base_query, clazz)

    return windowed_query(base_query, Document.document_id, batch_size)


def create_search_documents(doc_type, documents, batch):
    to_search_document = search_documents[doc_type].to_search_document
    index = elasticsearch_config['index']
    n = 0
    for doc in documents:
        batch.add(to_search_document(doc, index))
        n += 1
    log.info('Sent {} document(s) of type {}'.format(n, doc_type))

# association types that require an update
association_types_to_check = {
    # needed to update waypoint ids for routes
    (WAYPOINT_TYPE, ROUTE_TYPE),
    (WAYPOINT_TYPE, WAYPOINT_TYPE),
    # needed to update waypoint ids for outings (+ the 2 types above)
    # also needed to update route ids for outings
    (ROUTE_TYPE, OUTING_TYPE),
    # needed to update user ids for outings
    (USERPROFILE_TYPE, OUTING_TYPE)
}


def requires_updates(association):
    association_type = \
        (association.parent_document_type, association.child_document_type)
    return association_type in association_types_to_check
