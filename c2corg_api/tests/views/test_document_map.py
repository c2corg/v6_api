from datetime import date
from unittest.mock import patch

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document_map import (
    _geohash_center, _heatmap_precision, _lon_lat_to_3857)

BBOX = '635000,5723000,637000,5724000'


def _outing(title, activities, day, geom, geom_detail=None):
    return Outing(
        activities=activities, date_start=date(2016, 1, day),
        date_end=date(2016, 1, day),
        locales=[OutingLocale(lang='en', title=title)],
        geometry=DocumentGeometry(geom=geom, geom_detail=geom_detail))


def _route(title, activities, geom, geom_detail=None, title_prefix=None):
    return Route(
        activities=activities, elevation_max=1500, elevation_min=700,
        height_diff_up=800, height_diff_down=800, durations='1',
        locales=[RouteLocale(
            lang='en', title=title, title_prefix=title_prefix)],
        geometry=DocumentGeometry(geom=geom, geom_detail=geom_detail))


class TestHelpers(BaseTestRest):

    def test_geohash_center(self):
        lon, lat = _geohash_center('u09tun')
        self.assertAlmostEqual(lon, 2.29, places=1)
        self.assertAlmostEqual(lat, 48.86, places=1)

    def test_lon_lat_to_3857(self):
        x, y = _lon_lat_to_3857(0, 0)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 0)
        x, _ = _lon_lat_to_3857(180, 0)
        self.assertAlmostEqual(x, 20037508.34, places=1)

    def test_heatmap_precision(self):
        self.assertEqual(_heatmap_precision(0), 2)
        self.assertEqual(_heatmap_precision(8), 5)
        self.assertEqual(_heatmap_precision(12), 6)
        self.assertEqual(_heatmap_precision(30), 7)


class TestOutingsHeatmapRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestOutingsHeatmapRest, self).setUp()
        self._prefix = '/outings/map/heatmap'

        self.session.add(_outing(
            'Hike 1', ['hiking'], 1, 'SRID=3857;POINT(635956 5723604)'))
        self.session.add(_outing(
            'Hike 2', ['hiking'], 2, 'SRID=3857;POINT(635960 5723610)'))
        self.session.add(_outing(
            'Ski tour', ['skitouring'], 3, 'SRID=3857;POINT(635960 5723620)'))
        # far away, should never be returned by the bbox used in tests
        self.session.add(_outing(
            'Far away hike', ['hiking'], 4, 'SRID=3857;POINT(0 0)'))
        self.session.flush()
        reset_search_index(self.session)

    def test_missing_bbox(self):
        body = self.app.get(
            self._prefix + '?zoom=8', status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_missing_zoom(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX, status=400).json
        self.assertErrorsContain(body, 'zoom')

    def test_invalid_bbox(self):
        body = self.app.get(
            self._prefix + '?bbox=1,2,3&zoom=8', status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_heatmap(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX + '&zoom=8', status=200).json
        self.assertIn('buckets', body)
        total = sum(bucket['count'] for bucket in body['buckets'])
        # only the 3 outings within the bbox are counted, not the one
        # at (0, 0)
        self.assertEqual(total, 3)

    def test_heatmap_filtered_by_activity(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX + '&zoom=8&act=skitouring',
            status=200).json
        total = sum(bucket['count'] for bucket in body['buckets'])
        self.assertEqual(total, 1)

    def test_heatmap_filtered_by_date(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX +
            '&zoom=8&date=2016-01-01,2016-01-02', status=200).json
        total = sum(bucket['count'] for bucket in body['buckets'])
        self.assertEqual(total, 2)


class TestOutingsTracksRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestOutingsTracksRest, self).setUp()
        self._prefix = '/outings/map/tracks'

        self.outing1 = _outing(
            'Hike 1', ['hiking'], 1, 'SRID=3857;POINT(635956 5723604)',
            'SRID=3857;LINESTRING(635956 5723604, 635966 5723644)')
        self.session.add(self.outing1)
        self.outing2 = _outing(
            'Ski tour', ['skitouring'], 2, 'SRID=3857;POINT(635960 5723610)',
            'SRID=3857;LINESTRING(635960 5723610, 635970 5723650)')
        self.session.add(self.outing2)
        # no geom_detail: must never be returned by the tracks endpoint
        self.session.add(_outing(
            'No track', ['hiking'], 3, 'SRID=3857;POINT(635958 5723606)'))
        # the representative point is out of the bbox, but the track crosses
        # it: must be returned
        self.outing3 = _outing(
            'Long hike', ['hiking'], 4, 'SRID=3857;POINT(634800 5723500)',
            'SRID=3857;LINESTRING(634800 5723500, 635500 5723500)')
        self.session.add(self.outing3)
        self.session.flush()

        self.route = _route(
            'Route', ['hiking'], 'SRID=3857;POINT(635956 5723604)')
        self.session.add(self.route)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.route, child_document=self.outing1),
            user_id=self.global_userids['contributor'])
        self.session.flush()
        reset_search_index(self.session)

    def test_missing_bbox(self):
        body = self.app.get(self._prefix, status=400).json
        self.assertErrorsContain(body, 'bbox')

    def test_tracks(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX, status=200).json
        self.assertFalse(body['truncated'])
        titles = {o['title'] for o in body['documents']}
        self.assertEqual(titles, {'Hike 1', 'Ski tour', 'Long hike'})
        for outing in body['documents']:
            self.assertEqual(outing['type'], 'o')
            self.assertIn('geom_detail', outing['geometry'])

    def test_tracks_filtered_by_activity(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX + '&act=skitouring',
            status=200).json
        self.assertEqual(len(body['documents']), 1)
        self.assertEqual(body['documents'][0]['title'], 'Ski tour')

    def test_tracks_filtered_by_route(self):
        body = self.app.get(
            self._prefix + '?bbox=' + BBOX + '&r=' +
            str(self.route.document_id), status=200).json
        self.assertEqual(len(body['documents']), 1)
        self.assertEqual(
            body['documents'][0]['document_id'], self.outing1.document_id)

    def test_tracks_truncated(self):
        with patch('c2corg_api.views.document_map.TRACKS_LIMIT_MAX', 1):
            body = self.app.get(
                self._prefix + '?bbox=' + BBOX, status=200).json
        self.assertTrue(body['truncated'])
        self.assertEqual(body['documents'], [])

    def test_tracks_truncated_by_candidates(self):
        with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 1):
            body = self.app.get(
                self._prefix + '?bbox=' + BBOX, status=200).json
        self.assertTrue(body['truncated'])
        self.assertEqual(body['documents'], [])


class TestRoutesMapRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestRoutesMapRest, self).setUp()

        self.session.add(_route(
            'Hike route', ['hiking'], 'SRID=3857;POINT(635956 5723604)',
            'SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            title_prefix='Mont Blanc'))
        self.session.add(_route(
            'Ski route', ['skitouring'], 'SRID=3857;POINT(635960 5723610)',
            'SRID=3857;LINESTRING(635960 5723610, 635970 5723650)'))
        self.session.add(_route(
            'Far away route', ['hiking'], 'SRID=3857;POINT(0 0)',
            'SRID=3857;LINESTRING(0 0, 10 10)'))
        self.session.flush()
        reset_search_index(self.session)

    def test_heatmap(self):
        body = self.app.get(
            '/routes/map/heatmap?bbox=' + BBOX + '&zoom=8', status=200).json
        self.assertEqual(sum(b['count'] for b in body['buckets']), 2)

    def test_heatmap_filtered_by_activity(self):
        body = self.app.get(
            '/routes/map/heatmap?bbox=' + BBOX + '&zoom=8&act=skitouring',
            status=200).json
        self.assertEqual(sum(b['count'] for b in body['buckets']), 1)

    def test_tracks(self):
        body = self.app.get(
            '/routes/map/tracks?bbox=' + BBOX, status=200).json
        self.assertFalse(body['truncated'])
        titles = {r['title'] for r in body['documents']}
        self.assertEqual(titles, {'Mont Blanc : Hike route', 'Ski route'})
        for route in body['documents']:
            self.assertEqual(route['type'], 'r')

    def test_tracks_filtered_by_activity(self):
        body = self.app.get(
            '/routes/map/tracks?bbox=' + BBOX + '&act=hiking',
            status=200).json
        self.assertEqual(len(body['documents']), 1)
        self.assertEqual(
            body['documents'][0]['title'], 'Mont Blanc : Hike route')
