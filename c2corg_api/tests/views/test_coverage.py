import pytest

from c2corg_api.models.coverage import Coverage
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.tests import auth_headers, invalid_parameters, send_json

POLYGON = (
    '{"type": "Polygon", "coordinates": [[[635000, 5723000], [635000, 5724000], '
    '[637000, 5724000], [637000, 5723000], [635000, 5723000]]]}'
)


@pytest.fixture
def coverage_id(client):
    """Create a coverage through the API; return its id."""
    body = {
        'coverage_type': 'fr-se',
        'geometry': {'geom_detail': POLYGON},
        'locales': [{'lang': 'en', 'title': 'South-East'}],
    }
    response = send_json(
        client, 'post', '/coverages', body, headers=auth_headers(username='contributor')
    )
    return response.json['document_id']


def _put(client, session, coverage_id, change):
    document = client.get(f'/coverages/{coverage_id}').json
    change(document)
    body = {'message': 'update', 'document': document}
    send_json(
        client,
        'put',
        f'/coverages/{coverage_id}',
        body,
        headers=auth_headers(username='contributor'),
        status=200,
    )
    session.expire_all()
    return session.get(Coverage, coverage_id)


def _versions(session, coverage_id):
    return (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == coverage_id)
        .count()
    )


def test_listing_with_search_parameters(client, coverage_id):
    # the coverages are not indexed: the listing reads the database, it
    # used to look for a search mapping and answer 500
    for params in ({'q': 'South'}, {'pl': 'en', 'bbox': '0,0,1,1'}):
        response = client.get('/coverages', params=params, status=200)
        ids = [doc['document_id'] for doc in response.json['documents']]
        assert coverage_id in ids, params


def test_update_locale_only(client, session, coverage_id):
    # coverages have no history: an update used to look for the previous
    # archive and answer 500
    def change(document):
        document['locales'][0]['title'] = 'Sud-Est'

    coverage = _put(client, session, coverage_id, change)
    assert coverage.get_locale('en').title == 'Sud-Est'
    assert _versions(session, coverage_id) == 0


def test_update_figures(client, session, coverage_id):
    def change(document):
        document['coverage_type'] = 'fr-ne'

    coverage = _put(client, session, coverage_id, change)
    assert coverage.coverage_type == 'fr-ne'
    assert _versions(session, coverage_id) == 0


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
