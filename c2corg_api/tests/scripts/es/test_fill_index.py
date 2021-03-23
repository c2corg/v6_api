import datetime

from c2corg_api.models import es_sync
from c2corg_api.models.article import Article
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.search.mappings.article_mapping import SearchArticle
from c2corg_api.search.mappings.book_mapping import SearchBook
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.xreport_mapping import SearchXreport
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.tests import BaseTestCase
from c2corg_api.scripts.es.fill_index import fill_index


class FillIndexTest(BaseTestCase):

    def test_fill_index(self):
        """Tests that documents are inserted into the ElasticSearch index.
        """
        self.session.add(Waypoint(
            document_id=71171,
            waypoint_type='summit', elevation=2000, quality='medium',
            access_time='15min',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont [b]Granier[/b]'),
                WaypointLocale(
                    lang='en', title='Mont Granier',
                    description='...',
                    summary='The Mont Granier')
            ]))
        self.session.add(Waypoint(
            document_id=71172,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ]))
        self.session.add(Route(
            document_id=71173,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations=['1'],
            locales=[
                RouteLocale(
                    lang='en', title='Face N',
                    description='...', gear='paraglider',
                    title_prefix='Mont Blanc'
                )
            ]
        ))
        self.session.add(Waypoint(
            document_id=71174,
            redirects_to=71171,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ]))
        self.session.add(Outing(
            document_id=71175,
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1), frequentation='overcrowded',
            locales=[
                OutingLocale(
                    lang='en', title='Mont Blanc : Face N !',
                    description='...', weather='sunny')
            ]
        ))
        self.session.add(Article(
            document_id=71176,
            categories=['site_info'], activities=['hiking'],
            article_type='collab',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                DocumentLocale(
                    lang='en', title='Lac d\'Annecy',
                    description='...',
                    summary=''),
                DocumentLocale(
                    lang='fr', title='Lac d\'Annecy',
                    description='...',
                    summary='')
            ]))
        self.session.flush()

        self.session.add(Book(
            document_id=71177,
            activities=['hiking'],
            book_types=['biography'],
            author='Denis Dainat',
            publication_date='',
            locales=[
                DocumentLocale(
                    lang='fr', title='Escalades au Thaurac',
                    description='...',
                    summary=''),
                DocumentLocale(
                    lang='en', title='Escalades au Thaurac',
                    description='...',
                    summary=''
                )
            ]
        ))
        self.session.flush()

        self.session.add(Xreport(
            document_id=71178,
            event_type='person_fall',
            event_activity='skitouring',
            nb_participants=10,
            elevation=1500,
            date=datetime.date(2016, 1, 1),
            locales=[
                XreportLocale(
                    lang='en', title='Death in the mountains',
                    description='...',
                    place='some place description'
                )
            ]
        ))
        self.session.flush()

        # fill the ElasticSearch index
        fill_index(self.session)

        waypoint1 = SearchWaypoint.get(id=71171)
        self.assertIsNotNone(waypoint1)
        self.assertEqual(waypoint1.title_en, 'Mont Granier')
        self.assertEqual(waypoint1.title_fr, 'Mont Granier')
        # self.assertEqual(waypoint1.summary_fr, 'Le Mont  Granier ')
        self.assertEqual(waypoint1.doc_type, 'w')
        self.assertEqual(waypoint1.quality, 2)
        self.assertEqual(waypoint1.access_time, 3)
        self.assertAlmostEqual(waypoint1.geom[0], 5.71288994)
        self.assertAlmostEqual(waypoint1.geom[1], 45.64476395)

        waypoint2 = SearchWaypoint.get(id=71172)
        self.assertIsNotNone(waypoint2)
        self.assertEqual(waypoint2.title_en, 'Mont Blanc')
        self.assertIsNone(waypoint2.title_fr)
        self.assertEqual(waypoint2.doc_type, 'w')

        route = SearchRoute.get(id=71173)
        self.assertIsNotNone(route)
        self.assertEqual(route.title_en, 'Mont Blanc : Face N')
        self.assertIsNone(route.title_fr)
        self.assertEqual(route.doc_type, 'r')
        self.assertEqual(route.durations, [0])

        outing = SearchOuting.get(id=71175)
        self.assertIsNotNone(outing)
        self.assertEqual(outing.title_en, 'Mont Blanc : Face N !')
        self.assertIsNone(outing.title_fr)
        self.assertEqual(outing.doc_type, 'o')
        self.assertEqual(outing.frequentation, 3)

        article = SearchArticle.get(id=71176)
        self.assertIsNotNone(article)
        self.assertEqual(article.title_en, 'Lac d\'Annecy')
        self.assertEqual(article.title_fr, 'Lac d\'Annecy')
        self.assertEqual(article.doc_type, 'c')

        book = SearchBook.get(id=71177)
        self.assertIsNotNone(book)
        self.assertEqual(book.title_en, 'Escalades au Thaurac')
        self.assertEqual(book.title_fr, 'Escalades au Thaurac')
        self.assertEqual(book.doc_type, 'b')
        self.assertEqual(book.book_types, ['biography'])

        xreport = SearchXreport.get(id=71178)
        self.assertIsNotNone(xreport)
        self.assertEqual(xreport.title_en, 'Death in the mountains')
        self.assertEqual(xreport.doc_type, 'x')

        # merged document is ignored
        self.assertIsNone(SearchWaypoint.get(id=71174, ignore=404))

        # check that the sync. status was updated
        last_update, _ = es_sync.get_status(self.session)
        self.assertIsNotNone(last_update)
