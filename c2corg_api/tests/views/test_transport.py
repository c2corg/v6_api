from pyproj import Transformer

from c2corg_api.models.transport import TransportLine, TransportStop
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.transport.db_fixture import (
    WORLD, add_navitia_stops, import_test_feed)
from c2corg_api.transport.linking import link_transport_stops

# the Mairie stop (S2) of the fixture, in EPSG:3857
MAIRIE = Transformer.from_crs(4326, 3857, always_xy=True).transform(
    6.01, 45.01)


class TransportTestCase(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        import_test_feed(self.session)
        self.waypoint = add_navitia_stops(self.session)
        link_transport_stops(self.session)
        self.session.flush()

    def stop(self, stop_id):
        return self.session.query(TransportStop).filter_by(
            stop_id=stop_id).one()

    def line(self, route_id):
        return self.session.query(TransportLine).filter_by(
            route_id=route_id).one()


class TestStopsInBbox(TransportTestCase):

    def get(self, query=''):
        response = self.app.get(
            '/stopareas?bbox=' + WORLD + query, status=200)
        return {
            (stop['kind'], stop['stoparea_name']): stop
            for stop in response.json['documents']
        }

    def test_linked_gtfs_stops_and_unmatched_navitia_stops(self):
        stops = self.get()

        # S2 and S3 are linked to Navitia stops (S1 is not)
        self.assertEqual(set(stops), {
            ('gtfs', 'Mairie'),
            ('gtfs', 'Col'),
            # the Navitia stops that are not matched with a GTFS stop
            ('navitia', 'Gare (Ville)'),
            ('navitia', 'Ailleurs (Ville)'),
        })
        mairie = stops[('gtfs', 'Mairie')]
        self.assertEqual(mairie['id'], self.stop('S2').stop_pk)
        self.assertEqual(mairie['mode'], 'bus')
        self.assertTrue(mairie['linked'])
        self.assertAlmostEqual(mairie['coordinates']['x'], MAIRIE[0], delta=1)
        self.assertAlmostEqual(mairie['coordinates']['y'], MAIRIE[1], delta=1)
        # light: the details are read on click
        self.assertNotIn('details', mairie)

    def test_all_gtfs_stops(self):
        stops = self.get('&all=1')

        gare = stops[('gtfs', 'Gare')]
        self.assertFalse(gare['linked'])
        self.assertEqual(len(stops), 5)

    def test_navitia_stops_keep_their_lines_and_waypoints(self):
        stop = self.get()[('navitia', 'Ailleurs (Ville)')]

        self.assertEqual(stop['kind'], 'navitia')
        self.assertEqual(stop['navitia_id'], 'stop_area:Q:97')
        self.assertTrue(stop['linked'])
        self.assertEqual(
            [line['line'] for line in stop['lines']], ['Bus 1 - Gare - Col'])
        self.assertEqual(len(stop['waypoints']), 1)
        self.assertEqual(
            stop['waypoints'][0]['document_id'], self.waypoint.document_id)
        self.assertEqual(stop['waypoints'][0]['distance'], 2.5)

    def test_cache_header(self):
        response = self.app.get('/stopareas?bbox=' + WORLD, status=200)
        self.assertIn('max-age=86400', response.headers['Cache-Control'])

    def test_bbox_without_stop(self):
        response = self.app.get(
            '/stopareas?bbox=100000,100000,200000,200000&all=1', status=200)
        self.assertEqual(response.json['documents'], [])

    def test_bbox_is_limited_to_the_extent(self):
        # around the S2 stop only
        x, y = MAIRIE
        response = self.app.get(
            '/stopareas?bbox=%f,%f,%f,%f&all=1' % (
                x - 500, y - 500, x + 500, y + 500), status=200)
        self.assertEqual(
            [s['stoparea_name'] for s in response.json['documents']
             if s['kind'] == 'gtfs'], ['Mairie'])


class TestLinesInBbox(TransportTestCase):

    def test_lines(self):
        response = self.app.get('/transport-lines?bbox=' + WORLD, status=200)
        result = response.json

        self.assertEqual(result['type'], 'FeatureCollection')
        # R2 has no path
        self.assertEqual(len(result['features']), 1)
        feature = result['features'][0]
        self.assertEqual(feature['id'], self.line('R1').line_id)
        self.assertEqual(feature['geometry']['type'], 'MultiLineString')
        self.assertEqual(feature['properties'], {
            'line_id': self.line('R1').line_id,
            'short_name': '1',
            'long_name': 'Gare - Col',
            'mode': 'bus',
            'color': 'FF0000',
            'text_color': '000000',
        })
        self.assertIn(
            'max-age=86400', response.headers['Cache-Control'])

    def test_bbox_is_required(self):
        self.app.get('/transport-lines', status=400)

    def test_invalid_bbox(self):
        for bbox in ('abc', '1,2,3', '2000,0,0,2000', 'nan,0,1,1'):
            self.app.get('/transport-lines?bbox=' + bbox, status=400)

    def test_line_out_of_the_bbox(self):
        response = self.app.get(
            '/transport-lines?bbox=100000,100000,200000,200000', status=200)
        self.assertEqual(response.json['features'], [])


class TestLine(TransportTestCase):

    def test_line(self):
        line = self.line('R1')
        response = self.app.get(
            '/transport-lines/%d' % line.line_id, status=200)
        result = response.json

        self.assertEqual(result['short_name'], '1')
        self.assertEqual(result['operator'], 'Bus Alpes')
        self.assertEqual(result['url'], 'https://example.org/r1')
        self.assertEqual(result['feed']['license'], 'Licence Ouverte 2.0')
        self.assertEqual(result['feed']['attribution'], 'Test attribution')
        self.assertIsNotNone(result['feed']['imported_at'])
        self.assertIn('max-age=86400', response.headers['Cache-Control'])

        details = result['details']
        self.assertEqual(len(details['directions']), 2)
        outward = next(d for d in details['directions']
                       if d['direction_id'] == '0')
        stops = {s['stop_id']: s for s in outward['stops']}
        self.assertEqual(stops['S2']['stop_pk'], self.stop('S2').stop_pk)
        # only the stops linked to Navitia (so to a waypoint) are marked
        self.assertTrue(stops['S2']['linked'])
        self.assertTrue(stops['S3']['linked'])
        self.assertFalse(stops['S1']['linked'])

    def test_line_not_found(self):
        response = self.app.get('/transport-lines/999999', status=404)
        self.assertEqual(response.json['error'], 'Line not found')

    def test_invalid_id(self):
        self.app.get('/transport-lines/abc', status=400)


class TestStop(TransportTestCase):

    def test_linked_stop(self):
        stop = self.stop('S2')
        response = self.app.get(
            '/transport-stops/%d' % stop.stop_pk, status=200)
        result = response.json

        self.assertEqual(result['stoparea_name'], 'Mairie')
        self.assertEqual(result['feed']['license'], 'Licence Ouverte 2.0')
        self.assertIn('max-age=86400', response.headers['Cache-Control'])

        lines = result['details']['lines']
        self.assertEqual([line['route_id'] for line in lines], ['R1'])
        self.assertEqual(lines[0]['line_id'], self.line('R1').line_id)

        # the waypoints the Navitia stops of this stop are associated with
        self.assertEqual(len(result['waypoints']), 1)
        waypoint = result['waypoints'][0]
        self.assertEqual(waypoint['document_id'], self.waypoint.document_id)
        self.assertEqual(waypoint['distance'], 1.5)
        self.assertEqual(
            {locale['lang']: locale['title']
             for locale in waypoint['locales']},
            {'fr': 'Parking du Lac', 'en': 'Lake car park'})

    def test_stop_without_waypoint(self):
        response = self.app.get(
            '/transport-stops/%d' % self.stop('S1').stop_pk, status=200)

        self.assertEqual(response.json['waypoints'], [])
        # S1 is served by the bus and by the train
        self.assertEqual(
            {line['route_id'] for line in response.json['details']['lines']},
            {'R1', 'R2'})

    def test_stop_not_found(self):
        response = self.app.get('/transport-stops/999999', status=404)
        self.assertEqual(response.json['error'], 'Stop not found')
