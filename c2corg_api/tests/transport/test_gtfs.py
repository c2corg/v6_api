import unittest
from datetime import date

from c2corg_api.tests.transport.gtfs_fixture import TODAY, gtfs_archive
from c2corg_api.transport import gtfs


def runs(mask_hex, day):
    """Does the service run this day? (bit i of the mask: day start + i)"""
    return bool(int(mask_hex, 16) >> (day - TODAY).days & 1)


class TestRouteMode(unittest.TestCase):

    def test_route_mode(self):
        self.assertEqual(gtfs.route_mode('3'), 'bus')
        self.assertEqual(gtfs.route_mode('2'), 'train')
        self.assertEqual(gtfs.route_mode('0'), 'tram')
        self.assertEqual(gtfs.route_mode('109'), 'train')  # extended
        self.assertEqual(gtfs.route_mode('1300'), 'cable_car')
        self.assertEqual(gtfs.route_mode('9999'), 'bus')  # unknown
        self.assertEqual(gtfs.route_mode(''), 'bus')


class TestParse(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.parsed = gtfs.parse(gtfs_archive(), TODAY)
        cls.lines = {line['route_id']: line for line in cls.parsed['lines']}
        cls.stops = {stop['stop_id']: stop for stop in cls.parsed['stops']}

    def outward(self):
        return next(
            d for d in self.lines['R1']['details']['directions']
            if d['direction_id'] == '0')

    def test_lines(self):
        self.assertEqual(set(self.lines), {'R1', 'R2'})
        line = self.lines['R1']
        self.assertEqual(line['short_name'], '1')
        self.assertEqual(line['long_name'], 'Gare - Col')
        self.assertEqual(line['mode'], 'bus')
        self.assertEqual(line['color'], 'FF0000')
        self.assertEqual(line['text_color'], '000000')
        self.assertEqual(line['operator'], 'Bus Alpes')
        self.assertEqual(line['url'], 'https://example.org/r1')
        self.assertEqual(self.lines['R2']['mode'], 'train')
        self.assertIsNone(self.lines['R2']['color'])

    def test_path_is_merged_and_simplified(self):
        geom = self.lines['R1']['geom']
        self.assertEqual(geom.geom_type, 'MultiLineString')
        self.assertEqual(len(geom.geoms), 1)
        # the 11 points of the shape are on a straight line
        self.assertEqual(len(geom.geoms[0].coords), 2)
        # EPSG:3857, in meters
        self.assertGreater(abs(geom.geoms[0].coords[0][0]), 1000)

    def test_path_follows_the_shape(self):
        shape = (
            'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n'
            'SH1,45.000,6.000,1\nSH1,45.000,6.010,2\n'
            'SH1,45.010,6.010,3\nSH1,45.010,6.020,4\n')
        parsed = gtfs.parse(gtfs_archive(shapes=shape), TODAY)
        line = next(x for x in parsed['lines'] if x['route_id'] == 'R1')
        # a staircase is not simplified into a straight line
        self.assertEqual(len(line['geom'].geoms[0].coords), 4)

    def test_no_shape_no_path(self):
        self.assertIsNone(self.lines['R2']['geom'])

    def test_directions(self):
        directions = self.lines['R1']['details']['directions']
        self.assertEqual(len(directions), 2)
        outward = self.outward()
        # the platform is shown with its station
        self.assertEqual([s['stop_id'] for s in outward['stops']],
                         ['S1', 'S2', 'S3'])
        self.assertEqual(outward['label'], 'Gare → Col')
        self.assertEqual(outward['headsign'], 'Col')
        self.assertEqual(outward['origin'], 'Gare')
        self.assertEqual(outward['destination'], 'Col')

    def test_short_trip_is_shown_in_the_columns_of_the_main_one(self):
        times = sorted(trip['times'] for trip in self.outward()['trips'])
        # 08:00, 12:00 (stops at the second stop), 17:00 (arrives 25:10)
        self.assertEqual(times, [
            [480, 490, 505],
            [720, 730, None],
            [1020, 1030, 1510],
        ])

    def test_services(self):
        details = self.lines['R1']['details']
        self.assertEqual(details['start'], '2026-10-21')
        service_of = {
            tuple(t['times']): details['services'][t['service']]
            for t in self.outward()['trips']}
        weekdays = service_of[(480, 490, 505)]
        saturdays = service_of[(720, 730, None)]
        self.assertTrue(runs(weekdays, date(2026, 10, 21)))  # Wednesday
        self.assertFalse(runs(weekdays, date(2026, 10, 23)))  # removed
        self.assertFalse(runs(weekdays, date(2026, 10, 24)))  # Saturday
        self.assertTrue(runs(saturdays, date(2026, 10, 24)))
        self.assertTrue(runs(saturdays, date(2026, 10, 25)))  # added
        self.assertFalse(runs(saturdays, date(2026, 10, 21)))

    def test_services_are_shared(self):
        # the weekday service is used by 3 trips, the Saturday one by 1
        self.assertEqual(len(self.lines['R1']['details']['services']), 2)

    def test_stops(self):
        # S4 is not served
        self.assertEqual(set(self.stops), {'S1', 'S2', 'S3'})
        gare = self.stops['S1']
        self.assertEqual(gare['name'], 'Gare')
        self.assertEqual(gare['mode'], 'bus')
        self.assertEqual(gare['geom'].geom_type, 'Point')
        # the Navitia ids are built from them
        self.assertEqual(set(gare['ref_ids']), {'S1', 'S1a', 'QA'})

    def test_stop_departures_exclude_arrivals_at_the_terminus(self):
        col = self.stops['S3']
        lines = {line['route_id']: line for line in col['details']['lines']}
        # only the trip starting at S3 leaves from it (T3 at 09:00)
        self.assertEqual([d[0] for d in lines['R1']['departures']], [540])
        # the train (T5) ends here
        self.assertNotIn('R2', lines)

    def test_stop_lines(self):
        gare = self.stops['S1']
        lines = {line['route_id']: line for line in gare['details']['lines']}
        self.assertEqual(set(lines), {'R1', 'R2'})
        self.assertEqual(lines['R1']['short_name'], '1')
        self.assertEqual(lines['R1']['color'], 'FF0000')
        self.assertEqual(
            [d[0] for d in lines['R1']['departures']], [480, 720, 1020])
        self.assertEqual(sorted(lines['R1']['headsigns']), ['Col', 'Mairie'])

    def test_unserved_dates_drop_the_trips(self):
        calendar = (
            'service_id,monday,tuesday,wednesday,thursday,friday,saturday,'
            'sunday,start_date,end_date\n'
            'WK,1,1,1,1,1,0,0,20200101,20200131\n'
            'SAT,0,0,0,0,0,1,0,20261001,20271231\n')
        parsed = gtfs.parse(gtfs_archive(
            calendar=calendar,
            calendar_dates='service_id,date,exception_type\n'), TODAY)
        # the weekday service is over: only the Saturday trip remains
        self.assertEqual(
            {line['route_id'] for line in parsed['lines']}, {'R1'})
