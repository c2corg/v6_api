from dataclasses import dataclass

import pytest

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.views.scenarios import DocType

WAYPOINTS_STOPAREAS = DocType('/waypoints_stopareas', 'ws', WaypointStoparea)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: object
    waypoint2: object
    stoparea1: object
    stoparea2: object
    waypoint_stoparea1: object
    waypoint_stoparea2: object


@pytest.fixture(autouse=True)
def docs(session) -> Docs:
    waypoint1 = Waypoint(waypoint_type='summit', elevation=3779)

    locale_en = WaypointLocale(lang='en', title='Mont Pourri', access='y')
    waypoint1.locales.append(locale_en)

    session.add(waypoint1)
    session.flush()
    waypoint1 = waypoint1

    waypoint2 = Waypoint(waypoint_type='summit', elevation=3000)

    locale_en2 = WaypointLocale(lang='en', title='Another Summit', access='y')
    waypoint2.locales.append(locale_en2)

    session.add(waypoint2)
    session.flush()
    waypoint2 = waypoint2

    # Create stopareas for testing
    stoparea1 = Stoparea(
        stoparea_id=1,
        navitia_id='nav1',
        stoparea_name='Stop Area 1',
        line='line1',
        operator='operator1',
    )

    session.add(stoparea1)
    session.flush()
    stoparea1 = stoparea1

    stoparea2 = Stoparea(
        stoparea_id=2,
        navitia_id='nav2',
        stoparea_name='Stop Area 2',
        line='line2',
        operator='operator2',
    )

    session.add(stoparea2)
    session.flush()
    stoparea2 = stoparea2

    # Create waypoint-stoparea associations
    waypoint_stoparea1 = WaypointStoparea(
        waypoint_stoparea_id=1,
        waypoint_id=waypoint1.document_id,
        stoparea_id=stoparea1.stoparea_id,
        distance=100.0,
    )

    session.add(waypoint_stoparea1)
    session.flush()
    waypoint_stoparea1 = waypoint_stoparea1

    waypoint_stoparea2 = WaypointStoparea(
        waypoint_stoparea_id=2,
        waypoint_id=waypoint1.document_id,
        stoparea_id=stoparea2.stoparea_id,
        distance=200.0,
    )

    session.add(waypoint_stoparea2)
    session.flush()
    waypoint_stoparea2 = waypoint_stoparea2
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        stoparea1=stoparea1,
        stoparea2=stoparea2,
        waypoint_stoparea1=waypoint_stoparea1,
        waypoint_stoparea2=waypoint_stoparea2,
    )


def test_get_stopareas_by_waypoint(client, docs):
    """Test getting stopareas for a waypoint."""
    response = client.get(
        f'/waypoints/{docs.waypoint1.document_id}/stopareas', status=200
    )
    result = response.json

    assert result['waypoint_id'] == docs.waypoint1.document_id
    assert len(result['stopareas']) == 2

    stoparea1 = result['stopareas'][0]
    assert stoparea1['id'] == 1
    assert stoparea1['navitia_id'] == 'nav1'
    assert stoparea1['stoparea_name'] == 'Stop Area 1'
    assert stoparea1['line'] == 'line1'
    assert stoparea1['operator'] == 'operator1'
    assert stoparea1['distance'] == 100.0

    stoparea2 = result['stopareas'][1]
    assert stoparea2['id'] == 2
    assert stoparea2['navitia_id'] == 'nav2'
    assert stoparea2['stoparea_name'] == 'Stop Area 2'
    assert stoparea2['line'] == 'line2'
    assert stoparea2['operator'] == 'operator2'
    assert stoparea2['distance'] == 200.0


def test_get_stopareas_by_waypoint_not_found(client):
    """Test getting stopareas for a waypoint that doesn't exist."""
    # We'll test that it returns an empty array instead of 404
    response = client.get('/waypoints/999999/stopareas', status=200)
    result = response.json

    assert result['waypoint_id'] == 999999
    assert result['stopareas'] == []


def test_get_is_reachable_true(client, docs):
    """Test checking if a waypoint is reachable (has stopareas)."""
    response = client.get(
        f'/waypoints/{docs.waypoint1.document_id}/isReachable', status=200
    )
    result = response.json

    assert result


def test_get_is_reachable_false(client, docs):
    """Test checking if a waypoint is not reachable (no stopareas)."""
    response = client.get(
        f'/waypoints/{docs.waypoint2.document_id}/isReachable', status=200
    )
    result = response.json

    assert not result


def test_get_info(client, docs):
    """Test getting info for a waypoint-stoparea."""

    response = client.get('/waypoints_stopareas/1/en/info', status=200)
    result = response.json

    assert (
        result['waypoint_stoparea_id'] == docs.waypoint_stoparea1.waypoint_stoparea_id
    )
    assert result['attributes']['distance'] == 100.0
    assert result['attributes']['waypoint_id'] == docs.waypoint1.document_id
    assert result['attributes']['stoparea_id'] == 1


def test_get_info_not_found(client):
    """Test getting info for a waypoint-stoparea that doesn't exist."""
    response = client.get('/waypoints_stopareas/999999/en/info', status=404)
    assert response.json_body == {'error': 'Waypoint Stoparea not found'}


def test_get_info_lang_not_found(client):
    """Test getting info with an invalid lang."""
    response = client.get('/waypoints_stopareas/1/invalid/info', status=422)
    assert invalid_parameters(response) == [('path', 'lang', 'invalid lang')]
