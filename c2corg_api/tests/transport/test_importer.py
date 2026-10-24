from unittest import mock

from c2corg_api.models.transport import TransportFeed, TransportLine, TransportStop
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.transport.db_fixture import (
    FEED,
    OTHER_FEED,
    add_navitia_stops,
    import_test_feed,
)
from c2corg_api.tests.transport.gtfs_fixture import gtfs_archive
from c2corg_api.transport import importer
from c2corg_api.transport.importer import load_feeds
from c2corg_api.transport.linking import link_transport_stops
from c2corg_api.transport.postprocess import postprocess, report


class TestFeeds(BaseTestCase):
    def test_feeds_file(self):
        feeds = load_feeds()
        assert feeds
        assert len({f['id'] for f in feeds}) == len(feeds)
        for feed in feeds:
            for key in ('id', 'name', 'url', 'license', 'attribution'):
                assert feed[key], (feed['id'], key)


class TestImport(BaseTestCase):
    def test_save(self):
        import_test_feed(self.session)

        feed = self.session.get(TransportFeed, 'test')
        assert feed.name == FEED['name']
        assert feed.license == FEED['license']
        assert feed.checksum == 'checksum'
        assert feed.status == 'ok'
        assert feed.imported_at is not None

        lines = {
            line.route_id: line
            for line in self.session.query(TransportLine).filter_by(feed_id='test')
        }
        assert set(lines) == {'R1', 'R2'}
        assert lines['R1'].short_name == '1'
        assert lines['R1'].color == 'FF0000'
        assert lines['R1'].geom is not None
        assert lines['R2'].geom is None
        assert lines['R1'].details['start'] == '2026-10-21'

        stops = {
            stop.stop_id: stop
            for stop in self.session.query(TransportStop).filter_by(feed_id='test')
        }
        assert set(stops) == {'S1', 'S2', 'S3'}
        assert stops['S1'].mode == 'bus'
        assert set(stops['S1'].ref_ids) == {'S1', 'S1a', 'QA'}
        assert stops['S1'].navitia_ids == []

    def test_save_replaces_the_previous_import(self):
        import_test_feed(self.session)
        # the second import has only the first route, and not the S1 station
        routes = (
            'route_id,agency_id,route_short_name,route_long_name,'
            'route_type,route_color,route_text_color,route_url\n'
            'R1,A,1,Gare - Col,3,00FF00,000000,\n'
        )
        import_test_feed(self.session, routes=routes)

        lines = self.session.query(TransportLine).filter_by(feed_id='test')
        assert [line.route_id for line in lines] == ['R1']
        assert lines.one().color == '00FF00'
        assert self.session.query(TransportFeed).filter_by(feed_id='test').count() == 1

    def test_save_a_feed_without_trips(self):
        trips = 'route_id,service_id,trip_id,direction_id,trip_headsign,shape_id\n'
        import_test_feed(self.session, trips=trips)

        assert self.session.query(TransportLine).count() == 0
        assert self.session.query(TransportStop).count() == 0
        feed = self.session.get(TransportFeed, 'test')
        assert feed.status == 'ok'

    def test_gtfs_archive_helper(self):
        # the fixture is a valid archive, readable twice
        archive = gtfs_archive()
        assert archive.getvalue()


class TestLinking(BaseTestCase):
    def setUp(self):
        BaseTestCase.setUp(self)
        import_test_feed(self.session)
        add_navitia_stops(self.session)

    def navitia_ids(self):
        return {
            stop.stop_id: sorted(stop.navitia_ids)
            for stop in self.session.query(TransportStop).filter_by(feed_id='test')
        }

    def test_link_by_id_then_by_line_and_distance(self):
        link_transport_stops(self.session)
        self.session.expire_all()

        assert self.navitia_ids() == {
            'S1': [],  # the Navitia stop nearby has another line code
            'S2': ['stop_area:R:Navitia:S2'],  # id
            'S3': ['stop_area:Q:99'],  # line and distance
        }

    def test_link_is_recomputed(self):
        link_transport_stops(self.session)
        # stale links are removed
        self.session.query(TransportStop).filter_by(stop_id='S1').update(
            {'navitia_ids': ['stop_area:gone']}
        )
        link_transport_stops(self.session)
        self.session.expire_all()

        assert self.navitia_ids()['S1'] == []
        assert self.navitia_ids()['S2'] == ['stop_area:R:Navitia:S2']

    def test_a_stop_is_not_linked_twice_for_the_same_navitia_stop(self):
        link_transport_stops(self.session)
        # linked by id: the stop is not matched again by line and distance
        assert link_transport_stops(self.session) == 2


class TestImportFeeds(BaseTestCase):
    FEEDS = [
        dict(FEED, id='good', name='Good'),
        dict(FEED, id='broken', name='Broken'),
    ]

    def run_import(self, **kwargs):
        def download(url, path):
            if url.endswith('broken.zip'):
                raise OSError('network error')
            with open(path, 'wb') as f:
                f.write(gtfs_archive().getvalue())
            return 'checksum'

        feeds = [
            dict(feed, url='https://example.org/{}.zip'.format(feed['id']))
            for feed in self.FEEDS
        ]
        with (
            mock.patch.object(importer, 'load_feeds', return_value=feeds),
            mock.patch.object(importer, 'download', download),
        ):
            return importer.import_feeds(self.session, **kwargs)

    def test_a_failing_feed_does_not_prevent_the_others(self):
        assert self.run_import() == 1

        assert [feed.feed_id for feed in self.session.query(TransportFeed)] == ['good']
        assert self.session.query(TransportLine).count() == 2

    def test_an_unchanged_feed_is_skipped(self):
        assert self.run_import() == 1
        assert self.run_import() == 0
        assert self.run_import(force=True) == 1

    def test_only_the_requested_feeds(self):
        assert self.run_import(feed_ids=['broken']) == 0
        assert self.session.query(TransportFeed).count() == 0


class TestPostprocess(BaseTestCase):
    """The same feed twice: the stops and the lines are the same."""

    def setUp(self):
        BaseTestCase.setUp(self)
        import_test_feed(self.session)
        import_test_feed(self.session, feed=OTHER_FEED)

    def stops(self):
        self.session.expire_all()
        stops = self.session.query(TransportStop).order_by(TransportStop.stop_pk).all()
        return {(stop.feed_id, stop.stop_id): stop for stop in stops}

    def line(self, feed_id, route_id):
        self.session.expire_all()
        return (
            self.session.query(TransportLine)
            .filter_by(feed_id=feed_id, route_id=route_id)
            .one()
        )

    def test_each_stop_is_its_own_cluster_after_an_import(self):
        for stop in self.stops().values():
            assert stop.cluster_id == stop.stop_pk

    def test_the_stops_of_the_same_place_are_grouped(self):
        found = postprocess(self.session)

        stops = self.stops()
        for stop_id in ('S1', 'S2', 'S3'):
            anchor = stops[('test', stop_id)]
            member = stops[('other', stop_id)]
            # as many departures: the first stop is the anchor
            assert anchor.cluster_id == anchor.stop_pk
            assert member.cluster_id == anchor.stop_pk
        assert len(found['clusters']) == 3

    def test_the_duplicate_line_is_hidden(self):
        found = postprocess(self.session)

        kept, hidden = self.line('test', 'R1'), self.line('other', 'R1')
        assert kept.duplicate_of is None
        assert hidden.duplicate_of == kept.line_id
        assert found['hidden_lines'] == {hidden.line_id: kept.line_id}
        # no path: nothing to compare
        assert self.line('other', 'R2').duplicate_of is None

    def test_the_postprocess_can_be_done_again(self):
        postprocess(self.session)
        before = {key: stop.cluster_id for key, stop in self.stops().items()}
        postprocess(self.session)

        assert {key: stop.cluster_id for key, stop in self.stops().items()} == before
        assert self.line('other', 'R1').duplicate_of == self.line('test', 'R1').line_id

    def test_what_was_grouped_with_an_imported_feed_is_released(self):
        postprocess(self.session)

        # the anchors and the kept lines are the ones of the feed `test`
        import_test_feed(self.session)

        for (feed_id, _), stop in self.stops().items():
            assert stop.cluster_id == stop.stop_pk, feed_id
        assert self.line('other', 'R1').duplicate_of is None

    def test_a_far_stop_is_not_grouped(self):
        import_test_feed(
            self.session,
            feed=dict(FEED, id='far'),
            stops=(
                'stop_id,stop_name,stop_lat,stop_lon,location_type,'
                'parent_station,stop_code\n'
                'S1,Gare,46.0,7.0,1,,\nS1a,Gare quai A,46.0,7.0,0,S1,QA\n'
                'S2,Mairie,46.01,7.01,0,,\nS3,Col,46.02,7.02,0,,\n'
            ),
        )

        postprocess(self.session)

        stops = self.stops()
        assert stops['far', 'S1'].cluster_id == stops['far', 'S1'].stop_pk

    def test_the_report_shows_what_was_hidden(self):
        found = postprocess(self.session)

        lines = report(found)

        # the stops have the same names: only the hidden line
        assert len(lines) == 1
        assert 'hidden' in lines[0]
