from unittest import mock

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.transport import navitia
from c2corg_api.web import transport as transport_web

TODAY = navitia.paris_today()
TODAY_ISO = TODAY.isoformat()


def navitia_answers(nearby=None, stop_schedules=None, route_schedules=None, calls=None):
    """What Navitia answers, by kind of request."""

    def get_json(path, params=None):
        if calls is not None:
            calls.append(path)
        if path.endswith('/places_nearby'):
            return {'places_nearby': nearby or []}
        if path.startswith('/coord/'):
            return {'regions': ['fr-se']}
        if path.endswith('/stop_schedules'):
            return {'stop_schedules': stop_schedules or []}
        if path.endswith('/route_schedules'):
            return {'route_schedules': route_schedules or []}
        raise AssertionError('unexpected request ' + path)

    return get_json


def stop_schedule(code, line_id, times):
    return {
        'route': {'id': 'route:' + line_id, 'line': {'id': line_id}},
        'display_informations': {
            'code': code,
            'label': code,
            'name': 'Line ' + code,
            'color': 'AFCA0B',
            'text_color': 'FFFFFF',
            'network': 'Network',
            'commercial_mode': 'Coach',
            'direction': 'Annemasse',
        },
        'date_times': [
            {'date_time': TODAY.strftime('%Y%m%dT') + time + '00'} for time in times
        ],
    }


def route_schedule(direction, stops, trips):
    """stops: [(id, name)], trips: one list of 'HHMM' (or None) per trip."""
    rows = [
        {
            'stop_point': {
                'id': 'stop_point:' + stop_id,
                'name': name,
                'stop_area': {'id': 'stop_area:' + stop_id},
            },
            'date_times': [
                {'date_time': TODAY.strftime('%Y%m%dT') + trip[index] + '00'}
                if trip[index]
                else {'date_time': ''}
                for trip in trips
            ],
        }
        for index, (stop_id, name) in enumerate(stops)
    ]
    return {
        'display_informations': {'direction': direction},
        'table': {'headers': [{} for _ in trips], 'rows': rows},
    }


def no_cache(kind, key, creator):
    return creator()


def error_of(response):
    """The description of an error, as the application formats it."""
    return response.json['errors'][0]['description']


class TestTransportSchedules:
    @pytest.fixture(autouse=True)
    def documents(self, client, session):
        self.app = client
        self.session = session
        self._add_test_data()

    def _add_test_data(self):
        waypoint = Waypoint(waypoint_type='summit', elevation=2000)
        waypoint.locales.append(WaypointLocale(lang='fr', title='Parking du lac'))
        self.session.add(waypoint)
        route = Route(activities=['hiking'], elevation_max=2000)
        route.locales.append(RouteLocale(lang='fr', title='Tour du lac'))
        self.session.add(route)
        self.session.flush()
        self.session.add(Association.create(waypoint, route))
        self.session.add(
            Stoparea(
                stoparea_id=9101,
                navitia_id='stop_area:TEST:9101',
                stoparea_name='Gare du lac',
                line='A',
                operator='Operator',
            )
        )
        self.session.flush()
        self.session.add(
            WaypointStoparea(
                waypoint_id=waypoint.document_id, stoparea_id=9101, distance=0.7
            )
        )
        self.session.flush()
        self.waypoint = waypoint
        self.route = route

    def _get(self, url, status=200, **answers):
        # no cache: a test must not see the timetables of another
        with (
            mock.patch.object(navitia, 'get_json', navitia_answers(**answers)),
            mock.patch.object(transport_web, 'cached', no_cache),
        ):
            return self.app.get(url, status=status)

    def test_stop_schedules(self):
        response = self._get(
            f'/transport/stops/schedules?lon=1.11&lat=45.11&date={TODAY_ISO}'
            '&navitia_id=stop_area:TEST:9101&lang=fr',
            stop_schedules=[
                stop_schedule('B', 'line:B', []),
                stop_schedule('A', 'line:A', ['0605', '1700']),
            ],
        )

        body = response.json
        assert body['date'] == TODAY_ISO
        assert body['stop_area']['id'] == 'stop_area:TEST:9101'
        assert [line['code'] for line in body['lines']] == ['A', 'B']
        assert body['lines'][0]['departures'] == ['06:05', '17:00']
        assert body['next_date'] is None
        assert response.headers['Cache-Control'] == 'public, max-age=3600'

    def test_stop_schedules_with_what_the_stop_leads_to(self):
        body = self._get(
            f'/transport/stops/schedules?lon=1.12&lat=45.12&date={TODAY_ISO}'
            '&navitia_id=stop_area:TEST:9101&lang=fr',
            stop_schedules=[stop_schedule('A', 'line:A', ['0605'])],
        ).json

        associations = body['associations']
        assert associations['waypoints'] == [
            {
                'document_id': self.waypoint.document_id,
                'title': 'Parking du lac',
                'distance': 0.7,
            }
        ]
        assert associations['routes'] == [
            {'document_id': self.route.document_id, 'title': 'Tour du lac'}
        ]
        assert associations['outings'] == []

    def test_stop_found_by_its_position(self):
        calls = []
        near = {
            'id': 'stop_area:TEST:9101',
            'distance': '12',
            'stop_area': {
                'id': 'stop_area:TEST:9101',
                'name': 'Gare du lac',
                'coord': {'lon': '1.13', 'lat': '45.13'},
            },
        }

        body = self._get(
            f'/transport/stops/schedules?lon=1.13&lat=45.13&date={TODAY_ISO}'
            '&name=Gare du lac',
            nearby=[near],
            stop_schedules=[stop_schedule('A', 'line:A', ['0605'])],
            calls=calls,
        ).json

        assert body['stop_area']['id'] == 'stop_area:TEST:9101'
        assert body['associations']['waypoints'][0]['title'] == 'Parking du lac'
        assert [call.split('/')[-1] for call in calls] == [
            '1.13;45.13',
            'places_nearby',
            'stop_schedules',
        ]

    def test_unknown_stop(self):
        response = self._get(
            '/transport/stops/schedules?lon=1.14&lat=45.14', status=404, nearby=[]
        )

        assert error_of(response) == 'unknown_stop'

    def test_line_schedules(self):
        body = self._get(
            f'/transport/lines/schedules?lon=1.15&lat=45.15&date={TODAY_ISO}'
            '&ref=A&network=Network&lang=fr',
            nearby=[
                {
                    'id': 'stop_area:TEST:9101',
                    'distance': '300',
                    'stop_area': {
                        'id': 'stop_area:TEST:9101',
                        'name': 'Gare du lac',
                        'coord': {'lon': '1.15', 'lat': '45.15'},
                    },
                }
            ],
            stop_schedules=[stop_schedule('A', 'line:A', ['0605'])],
            route_schedules=[
                route_schedule(
                    'Annemasse',
                    [('TEST:9101', 'Gare du lac'), ('TEST:9102', 'Mairie')],
                    [['0605', '0615'], ['1700', None]],
                )
            ],
        ).json

        assert body['line']['line_id'] == 'line:A'
        assert body['directions'][0]['direction'] == 'Annemasse'
        assert [trip['times'] for trip in body['directions'][0]['trips']] == [
            ['06:05', '06:15'],
            ['17:00', None],
        ]
        assert body['associations']['routes'][0]['title'] == 'Tour du lac'

    def test_line_without_number(self):
        self._get('/transport/lines/schedules?lon=1.16&lat=45.16', status=422)

    def test_line_not_known_by_navitia(self):
        response = self._get(
            '/transport/lines/schedules?lon=1.17&lat=45.17&ref=Z9',
            status=404,
            nearby=[],
        )

        assert error_of(response) == 'unknown_line'

    @pytest.mark.parametrize(
        'query',
        [
            '',
            '?lon=abc&lat=45',
            '?lon=200&lat=45',
            '?lon=1&lat=95',
            '?lon=1&lat=45&lang=xx',
        ],
    )
    def test_invalid_parameters(self, query):
        # checked by FastAPI, as the typed parameters of the other routes
        self.app.get('/transport/stops/schedules' + query, status=422)

    @pytest.mark.parametrize(
        'date', ['26/10/2026', '20261026', '2999-01-01', '2000-01-01']
    )
    def test_invalid_date(self, date):
        response = self.app.get(
            f'/transport/stops/schedules?lon=1&lat=45&date={date}', status=400
        )

        assert response.json['errors'][0]['name'] == 'date'

    def test_errors_of_navitia_are_errors_of_the_api(self):
        for status in (404, 429, 502, 504):

            def failing(path, params=None, status=status):
                raise navitia.NavitiaError(status, 'failure')

            with (
                mock.patch.object(navitia, 'get_json', failing),
                mock.patch.object(transport_web, 'cached', no_cache),
            ):
                response = self.app.get(
                    f'/transport/stops/schedules?lon=1.{status}&lat=45.2',
                    status=status,
                )
            assert error_of(response) == 'failure'

    def test_the_answer_is_kept_for_the_next_click(self):
        calls = []
        answers = navitia_answers(
            stop_schedules=[stop_schedule('A', 'line:A', ['0605'])], calls=calls
        )
        memory = {}

        def cache(kind, key, creator):
            if (kind, key) not in memory:
                memory[(kind, key)] = creator()
            return memory[(kind, key)]

        url = (
            f'/transport/stops/schedules?lon=1.31&lat=45.31&date={TODAY_ISO}'
            '&navitia_id=stop_area:K:1'
        )
        with (
            mock.patch.object(navitia, 'get_json', answers),
            mock.patch.object(transport_web, 'cached', cache),
        ):
            first = self.app.get(url).json
            requests_made = len(calls)
            second = self.app.get(url).json

        assert first['lines'] == second['lines']
        assert requests_made == 2
        assert len(calls) == requests_made
