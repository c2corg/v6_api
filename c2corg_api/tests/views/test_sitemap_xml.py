from dataclasses import dataclass

import pytest

from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale

PREFIX = '/sitemaps.xml'

UI_URL = 'https://www.camptocamp.org'

SCHEMA_URL = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    route: Route


@pytest.fixture(autouse=True)
def docs(session) -> Docs:
    waypoint1 = Waypoint(
        waypoint_type='summit',
        elevation=2000,
        locales=[WaypointLocale(lang='fr', title='Dent de Crolles')],
    )
    session.add(waypoint1)
    waypoint2 = Waypoint(
        waypoint_type='summit',
        elevation=4985,
        locales=[
            WaypointLocale(lang='en', title='Mont Blanc'),
            WaypointLocale(lang='fr', title='Mont Blanc'),
        ],
    )
    session.add(waypoint2)
    route = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        locales=[
            RouteLocale(
                lang='fr', title='Mont Blanc du ciel', title_prefix='Mont Blanc'
            )
        ],
    )
    session.add(route)
    session.flush()
    return Docs(waypoint1=waypoint1, waypoint2=waypoint2, route=route)


def test_get(client):
    response = client.get(PREFIX, status=200)
    sitemaps = response.xml

    base_url = 'https://api.camptocamp.org/sitemaps.xml'

    def waypoint_filter(s):
        return s[0].text == base_url + '/w/0.xml'

    def route_filter(s):
        return s[0].text == base_url + '/r/0.xml'

    assert next(filter(waypoint_filter, sitemaps), None) is not None
    assert next(filter(route_filter, sitemaps), None) is not None


def test_get_sitemap_invalid_doc_type(client):
    response = client.get(PREFIX + '/z/0.xml', headers={'Cookie': 'a=b'}, status=422)
    # the errors only, as for the JSON routes: not the request headers
    assert response.json == {
        'detail': [
            {
                'type': 'c2corg',
                'loc': ['path', 'doc_type'],
                'msg': 'invalid doc_type',
                'input': 'z',
            }
        ]
    }


def test_get_sitemap_invalid_page(client):
    # a page that is not a number: not found
    client.get(PREFIX + '/a/-123.xml', status=404)


def test_get_waypoint_sitemap(client, docs):
    response = client.get(PREFIX + '/w/0.xml', status=200)
    urlset = response.xml

    assert len(urlset) == 3
    url = urlset[0]

    assert url[0].tag == f'{SCHEMA_URL}loc'
    assert url[1].tag == f'{SCHEMA_URL}lastmod'
    assert (
        url[0].text == f'{UI_URL}/waypoints/{docs.waypoint1.document_id}'
        '/fr/dent-de-crolles'
    )


def test_get_waypoint_sitemap_no_pages(client):
    client.get(PREFIX + '/w/1.xml', status=404)


def test_get_route_sitemap(client, docs):
    response = client.get(PREFIX + '/r/0.xml', status=200)
    urlset = response.xml

    assert len(urlset) == 1
    url = urlset[0]

    assert url[0].tag == f'{SCHEMA_URL}loc'
    assert url[1].tag == f'{SCHEMA_URL}lastmod'
    assert (
        url[0].text == f'{UI_URL}/routes/{docs.route.document_id}'
        '/fr/mont-blanc-mont-blanc-du-ciel'
    )
