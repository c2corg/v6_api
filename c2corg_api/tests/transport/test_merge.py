import unittest

from c2corg_api.transport.merge import line_key, merge_details


def mask(*days):
    return '%x' % sum(1 << day for day in days)


def details(start, services, *lines):
    return {'start': start, 'services': services, 'lines': list(lines)}


def line(short_name, departures, headsigns=('Col',), **kwargs):
    return {
        'route_id': 'R' + short_name, 'short_name': short_name, 'mode': 'bus',
        'color': 'FF0000', 'text_color': '000000',
        'headsigns': list(headsigns), 'departures': departures, **kwargs}


def runs(merged, service, day):
    """Does the service run the day `start + day`?"""
    return bool(int(merged['services'][service], 16) >> day & 1)


class TestMergeDetails(unittest.TestCase):

    def test_one_stop_is_unchanged_with_its_feed(self):
        stop = details('2026-10-21', {'s0': mask(0, 1)},
                       line('1', [[480, 's0', 0]]))

        merged = merge_details([('a', stop)])

        self.assertEqual(merged['start'], '2026-10-21')
        self.assertEqual(merged['services'], {'s0': mask(0, 1)})
        self.assertEqual(merged['lines'][0]['feed_id'], 'a')
        self.assertEqual(merged['lines'][0]['departures'], [[480, 's0', 0]])

    def test_the_line_of_two_feeds_is_one_line(self):
        a = details('2026-10-21', {'s0': mask(0, 1)},
                    line('Y62', [[480, 's0', 0]]))
        b = details('2026-10-21', {'s0': mask(0, 1)},
                    line('y62', [[600, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        self.assertEqual(len(merged['lines']), 1)
        # the line of the anchor
        self.assertEqual(merged['lines'][0]['feed_id'], 'a')
        self.assertEqual([d[0] for d in merged['lines'][0]['departures']],
                         [480, 600])

    def test_the_same_departure_in_two_feeds_is_shown_once(self):
        a = details('2026-10-21', {'s0': mask(0, 1)},
                    line('1', [[480, 's0', 0]]))
        b = details('2026-10-21', {'s0': mask(0, 1)},
                    line('1', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        self.assertEqual(len(merged['lines'][0]['departures']), 1)

    def test_the_same_departure_on_other_days_is_another_departure(self):
        a = details('2026-10-21', {'s0': mask(0)}, line('1', [[480, 's0', 0]]))
        b = details('2026-10-21', {'s0': mask(1)}, line('1', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        departures = merged['lines'][0]['departures']
        self.assertEqual(len(departures), 2)
        self.assertEqual(sorted(
            [runs(merged, d[1], 0), runs(merged, d[1], 1)]
            for d in departures), [[False, True], [True, False]])

    def test_the_days_of_a_departure_of_two_feeds_are_put_together(self):
        # the two feeds do not cover the same days, the first days of one and
        # the last days of the other are not compared
        a = details('2026-10-21', {'s0': mask(1, 2, 3)},
                    line('1', [[480, 's0', 0]]))
        b = details('2026-10-22', {'s0': mask(0, 1)},
                    line('1', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        self.assertEqual(merged['start'], '2026-10-21')
        departures = merged['lines'][0]['departures']
        self.assertEqual(len(departures), 1)
        # b runs the days 1 and 2 (it starts the day 1): the days 1, 2 and 3
        self.assertEqual(
            [runs(merged, departures[0][1], day) for day in range(5)],
            [False, True, True, True, False])

    def test_the_masks_follow_the_first_day(self):
        a = details('2026-10-22', {'s0': mask(0)}, line('1', [[480, 's0', 0]]))
        b = details('2026-10-21', {'s0': mask(5)}, line('2', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        self.assertEqual(merged['start'], '2026-10-21')
        lines = {x['short_name']: x for x in merged['lines']}
        # a runs the day 1 of the first day, b the day 5
        self.assertTrue(runs(merged, lines['1']['departures'][0][1], 1))
        self.assertFalse(runs(merged, lines['1']['departures'][0][1], 0))
        self.assertTrue(runs(merged, lines['2']['departures'][0][1], 5))

    def test_the_directions_of_the_feeds_are_put_together(self):
        a = details('2026-10-21', {'s0': mask(0)},
                    line('1', [[480, 's0', 0]], ['Col']))
        b = details(
            '2026-10-21', {'s0': mask(0)},
            line('1', [[480, 's0', 0], [500, 's0', 1]], ['Col', 'Gare']))

        merged = merge_details([('a', a), ('b', b)])

        departures = merged['lines'][0]['departures']
        headsigns = merged['lines'][0]['headsigns']
        self.assertEqual(headsigns, ['Col', 'Gare'])
        self.assertEqual([(d[0], headsigns[d[2]]) for d in departures],
                         [(480, 'Col'), (500, 'Gare')])

    def test_the_days_masks_are_shared(self):
        a = details('2026-10-21', {'s0': mask(0, 1), 's1': mask(2)},
                    line('1', [[480, 's0', 0], [500, 's1', 0]]))
        b = details('2026-10-21', {'s0': mask(0, 1)},
                    line('2', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        self.assertEqual(len(merged['services']), 2)

    def test_the_lines_of_the_two_feeds_are_kept(self):
        a = details('2026-10-21', {'s0': mask(0)}, line('1', [[480, 's0', 0]]))
        b = details('2026-10-21', {'s0': mask(0)}, line('2', [[480, 's0', 0]]))

        merged = merge_details([('a', a), ('b', b)])

        lines = merged['lines']
        self.assertEqual([x['short_name'] for x in lines], ['1', '2'])
        self.assertEqual([x['feed_id'] for x in lines], ['a', 'b'])

    def test_the_mode_makes_another_line(self):
        self.assertNotEqual(
            line_key(dict(line('1', []), mode='bus')),
            line_key(dict(line('1', []), mode='tram')))
        # the case and the order of the words do not matter
        self.assertEqual(line_key(line('Y62', [])), line_key(line('y62', [])))
        self.assertEqual(
            line_key(line('Y 62', [])), line_key(line('62 Y', [])))
