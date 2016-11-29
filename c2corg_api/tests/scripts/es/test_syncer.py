import transaction

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.syncer import SyncWorker
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.tests import BaseTestCase
from c2corg_api.views.document import DocumentRest


class SyncWorkerTest(BaseTestCase):

    def test_process_task(self):
        """Tests that the syncer listens to messages and sends changes to
        ElasticSearch.
        """
        waypoint = Waypoint(
            document_id=51251,
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont [b]Granier[/b]')
            ])
        self.session.add(waypoint)
        self.session.flush()
        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(waypoint, user_id)
        self.session.flush()

        t = transaction.begin()
        notify_es_syncer(self.queue_config)
        t.commit()

        syncer = SyncWorker(
            self.queue_config.connection, self.queue_config.queue, 1000,
            session=self.session)
        next(syncer.consume(limit=1))

        index = elasticsearch_config['index']
        doc = SearchWaypoint.get(id=51251, index=index)
        self.assertEqual(doc['title_fr'], 'Mont Granier')
        self.assertEqual(doc['summary_fr'], 'Le Mont  Granier ')
        self.assertEqual(doc['doc_type'], 'w')
