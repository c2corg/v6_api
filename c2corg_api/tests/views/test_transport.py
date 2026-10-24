import pytest
from pyproj import Transformer

from c2corg_api.models.transport import TransportLine, TransportStop
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.transport.db_fixture import (
    OTHER_FEED,
    WORLD,
    add_navitia_stops,
    import_test_feed,
)
from c2corg_api.transport.linking import link_transport_stops
from c2corg_api.transport.postprocess import postprocess

# the Mairie stop (S2) of the fixture, in EPSG:3857
MAIRIE = Transformer.from_crs(4326, 3857, always_xy=True).transform(6.01, 45.01)


class TransportTestCase(BaseTestCase):
    def setUp(self):
        BaseTestCase.setUp(self)
        import_test_feed(self.session)
        self.waypoint = add_navitia_stops(self.session)
        link_transport_stops(self.session)
        self.session.flush()

    def stop(self, stop_id):
        return self.session.query(TransportStop).filter_by(stop_id=stop_id).one()

    def line(self, route_id):
        return self.session.query(TransportLine).filter_by(route_id=route_id).one()


class TestStopsInBbox(TransportTestCase):
    def get(self, query=''):
        response = self.app.get('/stopareas?bbox=' + WORLD + query, status=200)
        return {
            (stop['kind'], stop['stoparea_name']): stop
            for stop in response.json['documents']
        }

    def test_linked_gtfs_stops_and_unmatched_navitia_stops(self):
        stops = self.get()

        # S2 and S3 are linked to Navitia stops (S1 is not)
        assert set(stops) == {
            ('gtfs', 'Mairie'),
            ('gtfs', 'Col'),
            # the Navitia stops that are not matched with a GTFS stop
            ('navitia', 'Gare (Ville)'),
            ('navitia', 'Ailleurs (Ville)'),
        }
        mairie = stops[('gtfs', 'Mairie')]
        assert mairie['id'] == self.stop('S2').stop_pk
        assert mairie['mode'] == 'bus'
        assert mairie['linked']
        assert mairie['coordinates']['x'] == pytest.approx(MAIRIE[0], abs=1)
        assert mairie['coordinates']['y'] == pytest.approx(MAIRIE[1], abs=1)
        # light: the details are read on click
        assert 'details' not in mairie

    def test_all_gtfs_stops(self):
        stops = self.get('&all=1')

        gare = stops[('gtfs', 'Gare')]
        assert not gare['linked']
        assert len(stops) == 5

    def test_navitia_stops_keep_their_lines_and_waypoints(self):
        stop = self.get()[('navitia', 'Ailleurs (Ville)')]

        assert stop['kind'] == 'navitia'
        assert stop['navitia_id'] == 'stop_area:Q:97'
        assert stop['linked']
        assert [line['line'] for line in stop['lines']] == ['Bus 1 - Gare - Col']
        assert len(stop['waypoints']) == 1
        assert stop['waypoints'][0]['document_id'] == self.waypoint.document_id
        assert stop['waypoints'][0]['distance'] == 2.5

    def test_cache_header(self):
        response = self.app.get('/stopareas?bbox=' + WORLD, status=200)
        assert 'max-age=86400' in response.headers['Cache-Control']

    def test_bbox_without_stop(self):
        response = self.app.get(
            '/stopareas?bbox=100000,100000,200000,200000&all=1', status=200
        )
        assert response.json['documents'] == []

    def test_bbox_is_limited_to_the_extent(self):
        # around the S2 stop only
        x, y = MAIRIE
        response = self.app.get(
            f'/stopareas?bbox={x - 500:f},{y - 500:f},{x + 500:f},{y + 500:f}&all=1',
            status=200,
        )
        assert [
            s['stoparea_name']
            for s in response.json['documents']
            if s['kind'] == 'gtfs'
        ] == ['Mairie']


class TestLinesInBbox(TransportTestCase):
    def test_lines(self):
        response = self.app.get('/transport-lines?bbox=' + WORLD, status=200)
        result = response.json

        assert result['type'] == 'FeatureCollection'
        # R2 has no path
        assert len(result['features']) == 1
        feature = result['features'][0]
        assert feature['id'] == self.line('R1').line_id
        assert feature['geometry']['type'] == 'MultiLineString'
        assert feature['properties'] == {
            'line_id': self.line('R1').line_id,
            'short_name': '1',
            'long_name': 'Gare - Col',
            'mode': 'bus',
            'color': 'FF0000',
            'text_color': '000000',
        }
        assert 'max-age=86400' in response.headers['Cache-Control']

    def test_bbox_is_required(self):
        self.app.get('/transport-lines', status=400)

    def test_invalid_bbox(self):
        for bbox in ('abc', '1,2,3', '2000,0,0,2000', 'nan,0,1,1'):
            self.app.get('/transport-lines?bbox=' + bbox, status=400)

    def test_line_out_of_the_bbox(self):
        response = self.app.get(
            '/transport-lines?bbox=100000,100000,200000,200000', status=200
        )
        assert response.json['features'] == []


class TestLine(TransportTestCase):
    def test_line(self):
        line = self.line('R1')
        response = self.app.get(f'/transport-lines/{line.line_id}', status=200)
        result = response.json

        assert result['short_name'] == '1'
        assert result['operator'] == 'Bus Alpes'
        assert result['url'] == 'https://example.org/r1'
        assert result['feed']['license'] == 'Licence Ouverte 2.0'
        assert result['feed']['attribution'] == 'Test attribution'
        assert result['feed']['imported_at'] is not None
        assert 'max-age=86400' in response.headers['Cache-Control']

        details = result['details']
        assert len(details['directions']) == 2
        outward = next(d for d in details['directions'] if d['direction_id'] == '0')
        stops = {s['stop_id']: s for s in outward['stops']}
        assert stops['S2']['stop_pk'] == self.stop('S2').stop_pk
        # only the stops linked to Navitia (so to a waypoint) are marked
        assert stops['S2']['linked']
        assert stops['S3']['linked']
        assert not stops['S1']['linked']

    def test_line_not_found(self):
        response = self.app.get('/transport-lines/999999', status=404)
        assert response.json['error'] == 'Line not found'

    def test_invalid_id(self):
        self.app.get('/transport-lines/abc', status=400)


class TestStop(TransportTestCase):
    def test_linked_stop(self):
        stop = self.stop('S2')
        response = self.app.get(f'/transport-stops/{stop.stop_pk}', status=200)
        result = response.json

        assert result['stoparea_name'] == 'Mairie'
        assert result['feed']['license'] == 'Licence Ouverte 2.0'
        assert 'max-age=86400' in response.headers['Cache-Control']

        lines = result['details']['lines']
        assert [line['route_id'] for line in lines] == ['R1']
        assert lines[0]['line_id'] == self.line('R1').line_id

        # the waypoints the Navitia stops of this stop are associated with
        assert len(result['waypoints']) == 1
        waypoint = result['waypoints'][0]
        assert waypoint['document_id'] == self.waypoint.document_id
        assert waypoint['distance'] == 1.5
        assert {locale['lang']: locale['title'] for locale in waypoint['locales']} == {
            'fr': 'Parking du Lac',
            'en': 'Lake car park',
        }

    def test_stop_without_waypoint(self):
        response = self.app.get(
            f'/transport-stops/{self.stop("S1").stop_pk}', status=200
        )

        assert response.json['waypoints'] == []
        # S1 is served by the bus and by the train
        assert {line['route_id'] for line in response.json['details']['lines']} == {
            'R1',
            'R2',
        }

    def test_stop_not_found(self):
        response = self.app.get('/transport-stops/999999', status=404)
        assert response.json['error'] == 'Stop not found'


class TestClusters(TransportTestCase):
    """The feed twice: the stops are one cluster, the lines are duplicates."""

    def setUp(self):
        TransportTestCase.setUp(self)
        import_test_feed(self.session, feed=OTHER_FEED)
        postprocess(self.session)
        self.session.flush()

    def stop_of(self, feed_id, stop_id):
        return (
            self.session.query(TransportStop)
            .filter_by(feed_id=feed_id, stop_id=stop_id)
            .one()
        )

    def stop(self, stop_id):
        return self.stop_of('test', stop_id)

    def line(self, route_id):
        # the kept line: the one of the first feed
        return (
            self.session.query(TransportLine)
            .filter_by(feed_id='test', route_id=route_id)
            .one()
        )

    def test_a_cluster_is_one_stop(self):
        response = self.app.get('/stopareas?bbox=' + WORLD + '&all=1', status=200)

        gtfs = [s for s in response.json['documents'] if s['kind'] == 'gtfs']
        assert sorted(s['stoparea_name'] for s in gtfs) == ['Col', 'Gare', 'Mairie']
        # the anchor is the one of the first feed
        mairie = next(s for s in gtfs if s['stoparea_name'] == 'Mairie')
        assert mairie['id'] == self.stop_of('test', 'S2').stop_pk
        assert mairie['linked']

    def test_a_stop_linked_in_a_feed_links_the_cluster(self):
        response = self.app.get('/stopareas?bbox=' + WORLD, status=200)

        names = {
            s['stoparea_name']
            for s in response.json['documents']
            if s['kind'] == 'gtfs'
        }
        assert names == {'Mairie', 'Col'}

    def test_the_details_of_a_member_are_the_ones_of_the_cluster(self):
        anchor = self.stop_of('test', 'S2')
        member = self.stop_of('other', 'S2')

        response = self.app.get(f'/transport-stops/{member.stop_pk}', status=200)
        alone = self.app.get(f'/transport-stops/{anchor.stop_pk}', status=200)

        assert response.json['id'] == anchor.stop_pk
        assert response.json['details'] == alone.json['details']
        assert [f['attribution'] for f in response.json['feeds']] == [
            'Test attribution',
            'Other attribution',
        ]
        assert response.json['feed']['attribution'] == 'Test attribution'

    def test_a_departure_of_two_feeds_is_shown_once(self):
        response = self.app.get(
            f'/transport-stops/{self.stop_of("test", "S1").stop_pk}', status=200
        )

        lines = {line['route_id']: line for line in response.json['details']['lines']}
        assert set(lines) == {'R1', 'R2'}
        assert [d[0] for d in lines['R1']['departures']] == [480, 720, 1020]

    def test_a_line_of_a_stop_is_the_kept_one(self):
        response = self.app.get(
            f'/transport-stops/{self.stop_of("other", "S1").stop_pk}', status=200
        )

        lines = {
            line['route_id']: line['line_id']
            for line in response.json['details']['lines']
        }
        assert lines['R1'] == self.line('R1').line_id

    def test_a_duplicate_line_is_hidden(self):
        response = self.app.get('/transport-lines?bbox=' + WORLD, status=200)

        assert [f['id'] for f in response.json['features']] == [self.line('R1').line_id]

    def test_a_hidden_line_gives_the_kept_line(self):
        hidden = (
            self.session.query(TransportLine)
            .filter_by(feed_id='other', route_id='R1')
            .one()
        )

        response = self.app.get(f'/transport-lines/{hidden.line_id}', status=200)

        assert response.json['line_id'] == self.line('R1').line_id
        assert response.json['feed']['attribution'] == 'Test attribution'
