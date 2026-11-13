import pytest

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.views.scenarios import DocType

STOPAREAS = DocType('/stopareas', 'sa', Stoparea)


@pytest.fixture(autouse=True)
def stoparea(session):
    """Add the stop area 1, read by id by the tests."""
    stoparea = Stoparea(
        stoparea_id=1,
        navitia_id='nav1',
        stoparea_name='Stop Area 1',
        line='line1',
        operator='operator1',
    )
    session.add(stoparea)
    session.flush()
    return stoparea


def test_collection_get(client):
    """Test getting list of stopareas."""
    response = client.get('/stopareas', status=200)
    result = response.json

    assert result['total_results'] >= 0
    assert isinstance(result['documents'], list)


def test_collection_get_page(client, session):
    session.add(
        Stoparea(
            stoparea_id=2,
            navitia_id='nav2',
            stoparea_name='Stop Area 2',
            line='line2',
            operator='operator2',
        )
    )
    session.flush()
    response = client.get('/stopareas?page_id=2&nb_items=1', status=200)
    result = response.json

    assert result['total_results'] == 2
    assert len(result['documents']) == 1


def test_collection_get_invalid_page(client):
    response = client.get('/stopareas?page_id=0&nb_items=x', status=422)
    names = [name for _, name, _ in invalid_parameters(response)]

    assert names == ['page_id', 'nb_items']


def test_get_stoparea_not_found(client):
    """Test getting a stoparea that doesn't exist."""
    response = client.get('/stopareas/999999', status=404)
    result = response.json

    assert result['errors'][0]['description'] == 'Stoparea not found'


def test_get_stoparea_found(client):
    """Test getting a stoparea that exists."""
    response = client.get('/stopareas/1', status=200)
    result = response.json

    assert result['id'] == 1
    assert result['navitia_id'] == 'nav1'
    assert result['stoparea_name'] == 'Stop Area 1'
    assert result['line'] == 'line1'
    assert result['operator'] == 'operator1'


def test_get_info_stoparea_not_found(client):
    """Test getting info for a stoparea that doesn't exist."""
    response = client.get('/stopareas/999999/fr/info', status=404)
    result = response.json

    assert result['errors'][0]['description'] == 'Stoparea not found'


def test_get_info_stoparea_found(client):
    """Test getting info for a stoparea that exists."""
    response = client.get('/stopareas/1/fr/info', status=200)
    result = response.json

    assert result['stoparea_id'] == 1
    assert result['attributes']['navitia_id'] == 'nav1'
    assert result['attributes']['stoparea_name'] == 'Stop Area 1'
    assert result['attributes']['line'] == 'line1'
    assert result['attributes']['operator'] == 'operator1'


def test_get_info_stoparea_lang_not_found(client):
    """Test getting info for a stoparea that doesn't exist."""
    response = client.get('/stopareas/1/invalid/info', status=422)
    assert invalid_parameters(response) == [('path', 'lang', 'invalid lang')]
