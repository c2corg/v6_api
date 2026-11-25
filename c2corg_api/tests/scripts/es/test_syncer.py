import pytest
from elasticsearch.exceptions import NotFoundError

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.es_sync import ESDeletedDocument
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.scripts.es.syncer import SyncWorker
from c2corg_api.search import index_name
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document import create_new_version


def test_process_task(session, user_ids, queue_config):
    """Tests that the syncer listens to messages and sends changes to
    ElasticSearch.
    """
    document_id = 51251
    waypoint = Waypoint(
        document_id=document_id,
        waypoint_type='summit',
        elevation=2000,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='fr',
                title='Mont Granier',
                description='...',
                summary='Le Mont [b]Granier[/b]',
            )
        ],
    )
    session.add(waypoint)
    session.flush()
    user_id = user_ids['contributor']
    create_new_version(waypoint, user_id)
    session.flush()

    # the notification is sent when the session of the views commits
    notify_es_syncer(queue_config)
    DBSession.commit()

    syncer = SyncWorker(
        queue_config.connection,
        queue_config.queue,
        1000,
        session=session,
    )
    next(syncer.consume(limit=1))

    index = index_name(WAYPOINT_TYPE)
    doc = SearchWaypoint.get(id=document_id, index=index)
    assert doc['title_fr'] == 'Mont Granier'
    assert doc['c2corg_doc_type'] == 'w'

    # simulate removing a document
    session.add(ESDeletedDocument(document_id=document_id, type=WAYPOINT_TYPE))
    session.flush()

    # the notification is sent when the session of the views commits
    notify_es_syncer(queue_config)
    DBSession.commit()

    next(syncer.consume(limit=1))
    with pytest.raises(NotFoundError):
        SearchWaypoint.get(id=document_id, index=index)
