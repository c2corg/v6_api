from unittest import mock

import pytest

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.transport.test_web import (
    TODAY_ISO,
    navitia_answers,
    no_cache,
    route_schedule,
    stop_schedule,
)
from c2corg_api.transport import navitia
from c2corg_api.web import transport as transport_web

STOP = ('GET', '/transport/stops/schedules')
LINE = ('GET', '/transport/lines/schedules')

NEARBY = [
    {
        'id': 'stop_area:TEST:9201',
        'distance': '40',
        'stop_area': {
            'id': 'stop_area:TEST:9201',
            'name': 'Gare de Chamonix',
            'coord': {'lon': '6.87', 'lat': '45.92'},
        },
    }
]


@pytest.fixture(autouse=True)
def stoparea(session):
    session.add(
        Stoparea(
            navitia_id='stop_area:TEST:9201',
            stoparea_name='Gare de Chamonix',
            line='A',
            operator='Operator',
        )
    )
    session.flush()


@pytest.fixture(autouse=True)
def fake_navitia():
    """Navitia answers without being asked, and nothing is kept in Redis."""
    answers = navitia_answers(
        nearby=NEARBY,
        stop_schedules=[stop_schedule('A', 'line:A', ['0605', '1700'])],
        route_schedules=[
            route_schedule(
                'Le Fayet',
                [('TEST:9201', 'Gare de Chamonix'), ('TEST:9202', 'Les Houches')],
                [['0605', '0620']],
            )
        ],
    )
    with (
        mock.patch.object(navitia, 'get_json', answers),
        mock.patch.object(transport_web, 'cached', no_cache),
    ):
        yield


class TestTransportStopSchedules:
    @contract(STOP)
    def test_stop(self, browser):
        response = browser.get(
            '/transport/stops/schedules',
            params={
                'lon': 6.87,
                'lat': 45.92,
                'date': TODAY_ISO,
                'navitia_id': 'stop_area:TEST:9201',
            },
        )
        check_snapshot('transport_stop_schedules', response)

    @contract(STOP)
    def test_invalid_date(self, browser):
        response = browser.get(
            '/transport/stops/schedules',
            params={'lon': 6.87, 'lat': 45.92, 'date': '2000-01-01'},
            status=400,
        )
        check_snapshot('transport_stop_schedules_invalid_date', response)


class TestTransportLineSchedules:
    @contract(LINE)
    def test_line(self, browser):
        response = browser.get(
            '/transport/lines/schedules',
            params={'lon': 6.87, 'lat': 45.92, 'date': TODAY_ISO, 'ref': 'A'},
        )
        check_snapshot('transport_line_schedules', response)

    @contract(LINE)
    def test_unknown_line(self, browser):
        response = browser.get(
            '/transport/lines/schedules',
            params={'lon': 6.87, 'lat': 45.92, 'date': TODAY_ISO, 'ref': 'Z9'},
            status=404,
        )
        check_snapshot('transport_line_schedules_unknown', response)
