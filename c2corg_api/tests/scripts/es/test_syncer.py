import pytest
import transaction
from elasticsearch.exceptions import NotFoundError

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.es_sync import ESDeletedDocument
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.scripts.es.syncer import SyncWorker
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.tests import BaseTestCase, global_userids
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class SyncWorkerTest(BaseTestCase):
    def test_process_task(self):
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
        self.session.add(waypoint)
        self.session.flush()
        user_id = global_userids['contributor']
        create_new_version(waypoint, user_id)
        self.session.flush()

        t = transaction.begin()
        notify_es_syncer(self.queue_config)
        t.commit()

        syncer = SyncWorker(
            self.queue_config.connection,
            self.queue_config.queue,
            1000,
            session=self.session,
        )
        next(syncer.consume(limit=1))

        index = elasticsearch_config['index']
        doc = SearchWaypoint.get(id=document_id, index=index)
        assert doc['title_fr'] == 'Mont Granier'
        assert doc['doc_type'] == 'w'

        # simulate removing a document
        self.session.add(ESDeletedDocument(document_id=document_id, type=WAYPOINT_TYPE))
        self.session.flush()

        t = transaction.begin()
        notify_es_syncer(self.queue_config)
        t.commit()

        next(syncer.consume(limit=1))
        with pytest.raises(NotFoundError):
            SearchWaypoint.get(id=document_id, index=index)
