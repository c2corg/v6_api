from datetime import date
from unittest.mock import patch

from c2corg_api.caching import cache_outing_map
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.tests.views import BaseTestRest


class TestOutingsHeatmapRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestOutingsHeatmapRest, self).setUp()
        self._prefix = '/outings/map/heatmap'
        # avoid cache hits from other tests reusing the same bbox
        cache_outing_map.invalidate()

        self.session.add(Outing(
            activities=['hiking'], date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[OutingLocale(lang='en', title='Hike 1')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)')))
        self.session.add(Outing(
            activities=['hiking'], date_start=date(2016, 1, 2),
            date_end=date(2016, 1, 2),
            locales=[OutingLocale(lang='en', title='Hike 2')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635960 5723610)')))
        self.session.add(Outing(
            activities=['skitouring'], date_start=date(2016, 1, 3),
            date_end=date(2016, 1, 3),
            locales=[OutingLocale(lang='en', title='Ski tour')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635960 5723620)')))
        # far away, should never be returned by the bbox used in tests
        self.session.add(Outing(
            activities=['hiking'], date_start=date(2016, 1, 4),
            date_end=date(2016, 1, 4),
            locales=[OutingLocale(lang='en', title='Far away hike')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(0 0)')))
        self.session.flush()

        self.bbox = '635000,5723000,637000,5724000'

    def test_missing_bbox(self):
        body = self.app.get(
            self._prefix + '?zoom=8', status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_missing_zoom(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox, status=400).json
        self.assertErrorsContain(body, 'zoom')

    def test_invalid_bbox(self):
        body = self.app.get(
            self._prefix + '?bbox=1,2,3&zoom=8', status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_invalid_activity(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox +
            '&zoom=8&act=cooking', status=400).json
        self.assertErrorsContain(body, 'act')

    def test_heatmap(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox + '&zoom=8', status=200) \
            .json
        self.assertIn('cell_size', body)
        self.assertIn('buckets', body)
        total = sum(bucket['count'] for bucket in body['buckets'])
        # only the 3 outings within the bbox are counted, not the one
        # at (0, 0)
        self.assertEqual(total, 3)

    def test_heatmap_filtered_by_activity(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox +
            '&zoom=8&act=skitouring', status=200).json
        total = sum(bucket['count'] for bucket in body['buckets'])
        self.assertEqual(total, 1)


class TestOutingsTracksRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestOutingsTracksRest, self).setUp()
        self._prefix = '/outings/map/tracks'
        # avoid cache hits from other tests reusing the same bbox
        cache_outing_map.invalidate()

        self.outing1 = Outing(
            activities=['hiking'], date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[OutingLocale(lang='en', title='Hike 1')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)',
                geom_detail='SRID=3857;LINESTRING(635956 5723604, '
                            '635966 5723644)'))
        self.session.add(self.outing1)

        self.outing2 = Outing(
            activities=['skitouring'], date_start=date(2016, 1, 2),
            date_end=date(2016, 1, 2),
            locales=[OutingLocale(lang='en', title='Ski tour')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635960 5723610)',
                geom_detail='SRID=3857;LINESTRING(635960 5723610, '
                            '635970 5723650)'))
        self.session.add(self.outing2)

        # no geom_detail: must never be returned by the tracks endpoint
        self.session.add(Outing(
            activities=['hiking'], date_start=date(2016, 1, 3),
            date_end=date(2016, 1, 3),
            locales=[OutingLocale(lang='en', title='No track')],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635958 5723606)')))
        self.session.flush()

        self.bbox = '635000,5723000,637000,5724000'

    def test_missing_bbox(self):
        body = self.app.get(self._prefix, status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_tracks(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox, status=200).json
        self.assertFalse(body['truncated'])
        self.assertEqual(len(body['outings']), 2)
        titles = {o['title'] for o in body['outings']}
        self.assertEqual(titles, {'Hike 1', 'Ski tour'})
        for outing in body['outings']:
            self.assertEqual(outing['type'], 'o')
            self.assertIn('geom_detail', outing['geometry'])

    def test_tracks_filtered_by_activity(self):
        body = self.app.get(
            self._prefix + '?bbox=' + self.bbox + '&act=skitouring',
            status=200).json
        self.assertEqual(len(body['outings']), 1)
        self.assertEqual(body['outings'][0]['title'], 'Ski tour')

    def test_tracks_truncated(self):
        with patch('c2corg_api.views.outing_map.TRACKS_LIMIT_MAX', 1):
            body = self.app.get(
                self._prefix + '?bbox=' + self.bbox, status=200).json
        self.assertTrue(body['truncated'])
        self.assertEqual(body['outings'], [])
