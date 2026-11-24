import json
from unittest.mock import Mock, patch

import pytest
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping

from c2corg_api.models.coverage import NavitiaCoverage
from c2corg_api.scripts.navitia import update_coverages
from c2corg_api.tests import invalid_parameters

# two coverages side by side; 'fr-ne' in two parts, as a coverage with islands
SOUTH_EAST = MultiPolygon([box(5, 44, 7, 46)])
NORTH_EAST = MultiPolygon([box(5, 46, 7, 48), box(8, 46, 9, 47)])


@pytest.fixture
def coverages(session):
    for name, shape in (('fr-se', SOUTH_EAST), ('fr-ne', NORTH_EAST)):
        session.add(
            NavitiaCoverage(coverage_type=name, geom=from_shape(shape, srid=4326))
        )
    session.flush()


def _polygon(*bounds):
    """Return the body of /getpolygoncoverage for a rectangle."""
    return {'geom_detail': json.dumps(mapping(box(*bounds)))}


@pytest.mark.usefixtures('coverages')
def test_lookup_of_a_point(client):
    for lon, lat, expected in (
        (6, 45, 'fr-se'),
        (6, 47, 'fr-ne'),
        # in the second part of a coverage
        (8.5, 46.5, 'fr-ne'),
        (0, 0, None),
    ):
        response = client.get(f'/getcoverage?lon={lon}&lat={lat}', status=200)
        assert response.json == expected, (lon, lat)


@pytest.mark.usefixtures('coverages')
def test_lookup_of_a_polygon(client):
    for bounds, expected in (
        ((5.5, 44.5, 6, 45), ['fr-se']),
        # across the border of the two coverages
        ((5.5, 45.5, 6, 46.5), ['fr-ne', 'fr-se']),
        ((0, 0, 1, 1), []),
    ):
        response = client.post_json('/getpolygoncoverage', _polygon(*bounds))
        assert response.json == expected, bounds


def test_lookup_outside_of_the_coverages(client):
    response = client.get('/getcoverage?lon=0&lat=0', status=200)
    assert response.json is None


def test_lookup_missing_parameters(client):
    response = client.get('/getcoverage', status=422)
    names = [name for _, name, _ in invalid_parameters(response)]
    assert names == ['lon', 'lat']


def test_lookup_invalid_parameters(client):
    response = client.get('/getcoverage?lon=x&lat=nan', status=422)
    names = [name for _, name, _ in invalid_parameters(response)]
    assert names == ['lon', 'lat']


def test_polygon_invalid_geom_detail(client):
    # a client error, not an unexpected one
    for body in ({}, {'geom_detail': 'not geojson'}, {'geom_detail': 42}):
        response = client.post_json('/getpolygoncoverage', body, status=400)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'geom_detail',
                'description': 'invalid geom_detail',
            }
        ]


def test_polygon_outside_of_the_coverages(client):
    body = {'geom_detail': '{"type": "Point", "coordinates": [6, 45]}'}
    assert client.post_json('/getpolygoncoverage', body).json == []


# the loader of the coverages (scripts/navitia/update_coverages.py)


def _navitia_response(regions):
    response = Mock()
    response.json.return_value = {'regions': regions}
    return response


def test_fetch_shape():
    shape = 'MULTIPOLYGON(((5 44,7 44,7 46,5 46,5 44)),((8 46,9 46,9 47,8 47,8 46)))'
    with patch.object(
        update_coverages.requests,
        'get',
        return_value=_navitia_response([{'id': 'fr-ne', 'shape': shape}]),
    ) as get:
        result = update_coverages.fetch_shape('fr-ne', 'key')
    assert get.call_args.args == (f'{update_coverages.BASE_URL}/coverage/fr-ne',)
    assert get.call_args.kwargs['headers'] == {'Authorization': 'key'}
    # both parts kept
    assert len(result.geoms) == 2


def test_fetch_shape_of_another_region():
    shape = 'POLYGON((5 44,7 44,7 46,5 46,5 44))'
    with (
        patch.object(
            update_coverages.requests,
            'get',
            return_value=_navitia_response([{'id': 'fr-se', 'shape': shape}]),
        ),
        pytest.raises(ValueError, match='unexpected regions'),
    ):
        update_coverages.fetch_shape('fr-ne', 'key')


def test_as_multipolygon():
    polygon = box(0, 0, 1, 1)
    assert update_coverages.as_multipolygon(polygon) == MultiPolygon([polygon])
    # a ring crossing itself
    bow_tie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    for shape in (Point(0, 0), MultiPolygon(), bow_tie):
        with pytest.raises(ValueError, match='not a valid multipolygon'):
            update_coverages.as_multipolygon(shape)


@pytest.mark.usefixtures('coverages')
def test_save_replaces_the_coverages(session):
    update_coverages.save({'fr-se': NORTH_EAST, 'fr-idf': SOUTH_EAST})
    session.expire_all()
    saved = {
        coverage.coverage_type: to_shape(coverage.geom)
        for coverage in session.query(NavitiaCoverage)
    }
    assert saved.keys() == {'fr-se', 'fr-idf'}
    assert saved['fr-se'].equals(NORTH_EAST)


def test_main_without_api_key(monkeypatch):
    monkeypatch.delenv('NAVITIA_API_KEY', raising=False)
    with pytest.raises(SystemExit, match='NAVITIA_API_KEY'):
        update_coverages.main(['update_navitia_coverages', 'production.ini'])
