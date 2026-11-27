import datetime
import json
import os
from unittest import mock

import pytest
import requests

from c2corg_api.transport import navitia
from c2corg_api.transport.navitia import DailyBudget, NavitiaError

DAY = datetime.date(2026, 10, 26)
LON, LAT = 6.7738, 46.0538


def direct(kind, key, creator):
    """No cache: always creates."""
    return creator()


class MemoryCache:
    def __init__(self):
        self.values = {}

    def __call__(self, kind, key, creator):
        if (kind, key) not in self.values:
            self.values[(kind, key)] = creator()
        return self.values[(kind, key)]


def place(stop_id, name, distance, lon=LON, lat=LAT):
    return {
        'id': stop_id,
        'name': name + ' (town)',
        'distance': str(distance),
        'embedded_type': 'stop_area',
        'stop_area': {
            'id': stop_id,
            'name': name,
            'coord': {'lon': str(lon), 'lat': str(lat)},
        },
    }


def stop_schedule(code, line_id, times, network='Haute-Savoie - Reseau 74'):
    return {
        'route': {'id': 'route:' + line_id, 'line': {'id': line_id}},
        'display_informations': {
            'code': code,
            'label': code,
            'name': 'Line ' + code,
            'color': 'AFCA0B',
            'text_color': 'FFFFFF',
            'network': network,
            'commercial_mode': 'Coach',
            'direction': 'Annemasse',
        },
        'date_times': [{'date_time': time} for time in times],
    }


class FakeNavitia:
    """Answers like Navitia, and remembers the paths asked for."""

    def __init__(self, stop_schedules=None, route_schedules=None, nearby=None):
        self.calls = []
        self.stop_schedules = stop_schedules or []
        self.route_schedules = route_schedules or []
        self.nearby = (
            nearby if nearby is not None else [place('stop_area:A', 'Gare', 7)]
        )

    def __call__(self, path, params=None):
        self.calls.append((path, params))
        if path.startswith('/coord/') and path.endswith('/places_nearby'):
            return {'places_nearby': self.nearby}
        if path.startswith('/coord/'):
            return {'regions': ['fr-se']}
        if path.endswith('/stop_schedules'):
            wide = params['duration'] > 86400
            return {'stop_schedules': self.stop_schedules if not wide else self.wide}
        if path.endswith('/route_schedules'):
            return {'route_schedules': self.route_schedules}
        raise AssertionError('unexpected path ' + path)

    wide = []

    def paths(self):
        return [path.split('/')[-1] for path, _ in self.calls]


@pytest.fixture
def fake(monkeypatch):
    fake = FakeNavitia()
    monkeypatch.setattr(navitia, 'get_json', fake)
    return fake


def test_date_times_are_read():
    assert navitia.parse_date_time('20261026T060500') == (DAY, '06:05')
    assert navitia.parse_date_time('') is None
    assert navitia.parse_date_time('20261326T060500') is None
    assert navitia.parse_date_time(None) is None


def test_names_are_compared_without_accents_or_punctuation():
    assert navitia.normalize('Gare Routière (Sixt)') == navitia.normalize(
        'gare routiere sixt'
    )
    assert navitia.normalize(None) == ''


def test_stop_area_with_the_same_name_is_preferred_to_the_nearest():
    candidates = [
        {'id': 'near', 'name': 'Mairie'},
        {'id': 'same', 'name': 'Gare Routière'},
    ]

    assert navitia.pick_stop_area(candidates, 'Gare routiere')['id'] == 'same'
    assert navitia.pick_stop_area(candidates, 'Unknown')['id'] == 'near'
    assert navitia.pick_stop_area(candidates)['id'] == 'near'
    assert navitia.pick_stop_area([], 'Gare') is None


def test_stop_areas_are_sorted_by_distance(fake):
    fake.nearby = [place('far', 'Far', 80), place('near', 'Near', 5)]

    found = navitia.find_stop_areas(LON, LAT, 100, 5, direct)

    assert [stop['id'] for stop in found] == ['near', 'far']
    assert found[0]['lon'] == LON


def test_departures_of_the_day_only():
    data = {
        'stop_schedules': [
            stop_schedule('B', 'line:B', []),
            stop_schedule(
                'A',
                'line:A',
                [
                    '20261026T170000',
                    '20261026T060500',
                    '20261026T060500',
                    '20261027T060500',
                ],
            ),
        ]
    }

    lines = navitia.parse_stop_schedules(data, DAY)

    # lines that run come first
    assert [line['code'] for line in lines] == ['A', 'B']
    assert lines[0]['departures'] == ['06:05', '17:00']
    assert lines[0]['line_id'] == 'line:A'
    assert lines[0]['color'] == 'AFCA0B'
    assert lines[0]['mode'] == 'Coach'
    assert lines[1]['departures'] == []


def test_next_day_with_a_departure():
    data = {
        'stop_schedules': [
            stop_schedule(
                'A', 'line:A', ['20261030T060500', '20261028T060500', '20261026T080000']
            )
        ]
    }

    assert navitia.next_running_date(data, DAY) == '2026-10-28'
    assert navitia.next_running_date({'stop_schedules': []}, DAY) is None


def test_stop_timetable_makes_three_requests_then_none(fake):
    fake.stop_schedules = [stop_schedule('A', 'line:A', ['20261026T060500'])]
    cache = MemoryCache()

    first = navitia.stop_timetable(LON, LAT, DAY, cache, name='Gare')
    second = navitia.stop_timetable(LON, LAT, DAY, cache, name='Gare')

    assert first == second
    assert first['stop_area']['id'] == 'stop_area:A'
    assert first['lines'][0]['departures'] == ['06:05']
    assert first['next_date'] is None
    # region, stop areas around, timetable
    assert fake.paths() == ['6.7738;46.0538', 'places_nearby', 'stop_schedules']
    _, params = fake.calls[-1]
    assert params['data_freshness'] == 'base_schedule'
    assert params['from_datetime'] == '20261026T000000'


def test_stop_timetable_of_a_known_stop_area_skips_the_search(fake):
    fake.stop_schedules = [stop_schedule('A', 'line:A', ['20261026T060500'])]

    result = navitia.stop_timetable(LON, LAT, DAY, direct, navitia_id='stop_area:KNOWN')

    assert result['stop_area']['id'] == 'stop_area:KNOWN'
    assert 'places_nearby' not in fake.paths()
    assert '/stop_areas/stop_area%3AKNOWN/' in fake.calls[-1][0]


def test_a_day_without_service_gives_the_next_one(fake):
    fake.stop_schedules = [stop_schedule('A', 'line:A', [])]
    fake.wide = [stop_schedule('A', 'line:A', ['20261102T060500'])]

    result = navitia.stop_timetable(LON, LAT, DAY, direct, name='Gare')

    assert result['next_date'] == '2026-11-02'
    assert fake.paths().count('stop_schedules') == 2


def test_no_stop_area_nearby(fake):
    fake.nearby = []

    assert navitia.stop_timetable(LON, LAT, DAY, direct) is None


def test_line_is_found_by_its_number_among_the_nearby_stops(fake):
    fake.nearby = [
        place('stop_area:A', 'Gare', 300),
        place('stop_area:B', 'Mairie', 900),
    ]
    fake.stop_schedules = [
        stop_schedule('Y01', 'line:Y01', ['20261026T060500']),
        stop_schedule('y02', 'line:Y02', ['20261026T060500']),
    ]

    line = navitia.find_line(LON, LAT, 'Y02', 'Cars Région Haute-Savoie', DAY, direct)

    assert line['line_id'] == 'line:Y02'
    # the first stop is enough
    assert fake.paths().count('stop_schedules') == 1


def test_line_with_the_most_similar_network_wins(fake):
    fake.stop_schedules = [
        stop_schedule(
            '1', 'line:other', ['20261026T060500'], network='Reseau urbain Grenoble'
        ),
        stop_schedule('1', 'line:ours', ['20261026T060500'], network='Annecy Sibra'),
    ]

    line = navitia.find_line(LON, LAT, '1', 'Sibra Annecy', DAY, direct)

    assert line['line_id'] == 'line:ours'


def test_line_not_known_by_navitia(fake):
    fake.stop_schedules = [stop_schedule('A', 'line:A', ['20261026T060500'])]

    assert navitia.find_line(LON, LAT, 'Z9', None, DAY, direct) is None
    assert navitia.line_timetable(LON, LAT, 'Z9', None, DAY, direct) is None


def route_schedule(direction, stops, columns):
    """stops: [(id, name)]; columns: one list of times (or None) per trip."""
    rows = []
    for index, (stop_id, name) in enumerate(stops):
        rows.append(
            {
                'stop_point': {
                    'id': 'stop_point:' + stop_id,
                    'name': name,
                    'stop_area': {'id': 'stop_area:' + stop_id},
                },
                'date_times': [
                    {'date_time': column[index] or ''} for column in columns
                ],
            }
        )
    return {
        'display_informations': {'direction': direction},
        'table': {'headers': [{} for _ in columns], 'rows': rows},
    }


def test_route_schedules_are_read_trip_by_trip():
    data = {
        'route_schedules': [
            route_schedule(
                'Sixt',
                [('A', 'Annemasse'), ('B', 'Cluses'), ('C', 'Sixt')],
                [
                    ['20261026T060500', '20261026T070500', '20261026T074500'],
                    ['20261027T060500', '20261027T070500', '20261027T074500'],
                    ['20261026T170500', None, '20261026T182000'],
                ],
            )
        ]
    }

    directions, stop_area_ids = navitia.parse_route_schedules(data, DAY)

    assert stop_area_ids == ['stop_area:A', 'stop_area:B', 'stop_area:C']
    assert len(directions) == 1
    assert directions[0]['direction'] == 'Sixt'
    assert [stop['name'] for stop in directions[0]['stops']] == [
        'Annemasse',
        'Cluses',
        'Sixt',
    ]
    # the trip of another day is left out
    assert directions[0]['trips'] == [
        {'times': ['06:05', '07:05', '07:45'], 'on_demand': False},
        {'times': ['17:05', None, '18:20'], 'on_demand': False},
    ]


def test_line_timetable_is_cached_for_the_next_click(fake):
    fake.stop_schedules = [stop_schedule('Y02', 'line:Y02', ['20261026T060500'])]
    fake.route_schedules = [
        route_schedule(
            'Sixt',
            [('A', 'Annemasse'), ('C', 'Sixt')],
            [['20261026T060500', '20261026T074500']],
        )
    ]
    cache = MemoryCache()

    first = navitia.line_timetable(LON, LAT, 'Y02', 'Cars', DAY, cache)
    requests_made = len(fake.calls)
    second = navitia.line_timetable(LON, LAT, 'Y02', 'Cars', DAY, cache)

    assert first == second
    assert first['line']['line_id'] == 'line:Y02'
    assert first['stop_area_ids'] == ['stop_area:A', 'stop_area:C']
    assert first['next_date'] is None
    assert len(fake.calls) == requests_made
    # region, stop areas around, line search, route schedules
    assert fake.paths() == [
        '6.7738;46.0538',
        'places_nearby',
        'stop_schedules',
        'route_schedules',
    ]


def test_line_without_trips_that_day_gives_the_next_day(fake):
    fake.stop_schedules = [stop_schedule('Y02', 'line:Y02', [])]
    fake.route_schedules = [route_schedule('Sixt', [('A', 'Annemasse')], [[None]])]

    def wide_route_schedules(path, params=None):
        if path.endswith('/route_schedules') and params['duration'] > 86400:
            return {
                'route_schedules': [
                    route_schedule('Sixt', [('A', 'Annemasse')], [['20261102T060500']])
                ]
            }
        return FakeNavitia.__call__(fake, path, params)

    with mock.patch.object(navitia, 'get_json', wide_route_schedules):
        result = navitia.line_timetable(LON, LAT, 'Y02', None, DAY, direct)

    assert result['directions'][0]['trips'] == []
    assert result['next_date'] == '2026-11-02'


def test_daily_budget_stops_the_requests_beyond_the_cap():
    counts = iter([1, 2, 3])
    budget = DailyBudget(2, counter=lambda day: next(counts), today=lambda: DAY)

    budget.consume()
    budget.consume()
    with pytest.raises(NavitiaError) as error:
        budget.consume()
    assert error.value.status == 429


def test_daily_budget_is_ignored_when_unlimited_or_when_the_counter_is_down():
    DailyBudget(0, counter=lambda day: 10**9).consume()
    DailyBudget(5).consume()

    def broken(day):
        raise ConnectionError

    DailyBudget(5, counter=broken).consume()


def answer(status):
    response = mock.Mock(status_code=status, ok=status < 400)
    response.json.return_value = {'ok': True}
    return response


@pytest.mark.parametrize(
    'status, expected',
    [(404, 404), (400, 400), (500, 502), (403, 502), (429, 502)],
)
def test_navitia_errors_become_errors_of_the_api(monkeypatch, status, expected):
    monkeypatch.setenv('NAVITIA_API_KEY', 'key')
    with mock.patch.object(requests, 'get', return_value=answer(status)):
        with pytest.raises(NavitiaError) as error:
            navitia.get_json('/coverage/fr-se/lines')
    assert error.value.status == expected


def test_navitia_timeout_and_missing_key(monkeypatch):
    monkeypatch.setenv('NAVITIA_API_KEY', 'key')
    with mock.patch.object(requests, 'get', side_effect=requests.exceptions.Timeout):
        with pytest.raises(NavitiaError) as error:
            navitia.get_json('/x')
    assert error.value.status == 504

    monkeypatch.delenv('NAVITIA_API_KEY')
    with pytest.raises(NavitiaError) as error:
        navitia.get_json('/x')
    assert error.value.status == 500


def test_navitia_request_carries_the_key_and_the_parameters(monkeypatch):
    monkeypatch.setenv('NAVITIA_API_KEY', 'secret')
    with mock.patch.object(requests, 'get', return_value=answer(200)) as get:
        assert navitia.get_json('/coord/1;2', {'a': 1}) == {'ok': True}

    args, kwargs = get.call_args
    assert args[0] == 'https://api.navitia.io/v1/coord/1;2'
    assert kwargs['headers'] == {'Authorization': 'secret'}
    assert kwargs['params'] == {'a': 1}


def test_a_point_without_coverage(monkeypatch):
    monkeypatch.setattr(navitia, 'get_json', lambda path, params=None: {'regions': []})

    with pytest.raises(NavitiaError) as error:
        navitia.region_of(0.0, 0.0, direct)
    assert error.value.status == 404


def test_on_demand_departures_of_a_stop_are_flagged():
    schedule = stop_schedule('Y02', 'line:Y02', ['20261026T060500', '20261026T170000'])
    schedule['date_times'][1]['additional_informations'] = ['on_demand_transport']

    lines = navitia.parse_stop_schedules({'stop_schedules': [schedule]}, DAY)

    assert lines[0]['departures'] == ['06:05', '17:00']
    assert lines[0]['on_demand'] == ['17:00']


def test_on_demand_trips_of_a_line_are_flagged():
    data = {
        'route_schedules': [
            route_schedule(
                'Sixt',
                [('A', 'Annemasse'), ('B', 'Sixt')],
                [
                    ['20261026T060500', '20261026T070500'],
                    ['20261026T170500', '20261026T180500'],
                ],
            )
        ]
    }
    table = data['route_schedules'][0]['table']
    table['headers'][0]['additional_informations'] = ['odt_with_stop_time']
    table['rows'][0]['date_times'][1]['additional_informations'] = [
        'on_demand_transport'
    ]

    directions, _ = navitia.parse_route_schedules(data, DAY)

    assert [trip['on_demand'] for trip in directions[0]['trips']] == [True, True]
    del table['headers'][0]['additional_informations']
    directions, _ = navitia.parse_route_schedules(data, DAY)
    assert [trip['on_demand'] for trip in directions[0]['trips']] == [False, True]


def test_a_real_route_schedules_answer_of_navitia():
    """Shortened answer of Navitia for the line Y02 of Haute-Savoie, a Monday."""
    path = os.path.join(os.path.dirname(__file__), 'navitia_route_schedules.json')
    with open(path, encoding='utf-8') as answer:
        data = json.load(answer)

    directions, stop_area_ids = navitia.parse_route_schedules(data, DAY)

    assert len(directions) == 2
    assert len(stop_area_ids) == 6
    towards_sixt, towards_annemasse = directions
    assert [stop['name'] for stop in towards_sixt['stops']][0] == 'Gare Routière'
    # the first and third trips run on demand
    assert [trip['on_demand'] for trip in towards_sixt['trips']] == [True, False, True]
    assert towards_sixt['trips'][0]['times'][0] == '08:35'
    # Navitia leaves a cell empty when a trip does not call at a stop
    assert towards_annemasse['trips'][0]['times'][0] == '06:05'
    assert all(len(trip['times']) == 3 for trip in towards_annemasse['trips'])


def test_a_real_stop_schedules_answer_of_navitia():
    """Answer of Navitia for the stop of Sixt-Fer-à-Cheval, a Monday."""
    path = os.path.join(os.path.dirname(__file__), 'navitia_stop_schedules.json')
    with open(path, encoding='utf-8') as answer:
        data = json.load(answer)

    lines = navitia.parse_stop_schedules(data, DAY)

    # the lines that run come first
    assert [(line['code'], bool(line['departures'])) for line in lines] == [
        ('Y02', True),
        ('Y94', True),
        ('Y02', False),
        ('Y94', False),
    ]
    assert lines[0]['departures'] == ['06:05', '06:55', '09:40', '12:30', '15:30']
    assert lines[0]['on_demand'] == ['09:40']
    assert lines[0]['line_id'] == 'line:R74:HAUTExSAVOIE:Line:1007006:LOC'
    assert lines[1]['departures'] == ['06:45', '10:15', '19:15']
    assert lines[0]['color'] == 'AFCA0B'
