from dataclasses import dataclass
from urllib.parse import quote

import pytest

from c2corg_api.models.article import Article
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.tests import auth_headers
from c2corg_api.tests.search import force_search_index

PREFIX = '/search'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    article1: Article
    waypoint1: Waypoint
    book1: Book


@pytest.fixture(autouse=True)
def docs(session) -> Docs:
    article1 = Article(
        categories=['site_info'],
        activities=['hiking'],
        article_type='collab',
        locales=[
            DocumentLocale(
                lang='en',
                title="Lac d'Annecy",
                description='...',
                summary="Lac d'Annecy",
            ),
            DocumentLocale(
                lang='en',
                title="Lac d'Annecy",
                description='...',
                summary="Lac d'Annecy",
            ),
        ],
    )
    session.add(article1)
    waypoint1 = Waypoint(
        waypoint_type='summit',
        elevation=2000,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='fr',
                title='Dent de Crolles',
                description='...',
                summary='La Dent de Crolles',
            ),
            WaypointLocale(
                lang='en',
                title='Dent de Crolles',
                description='...',
                summary='The Dent de Crolles',
            ),
        ],
    )
    session.add(waypoint1)
    session.add(
        Waypoint(
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
    )
    # a title that shares an ngram prefix with "Mont Blanc" once split
    # on the hyphen (regression fixture, see
    # test_search_hyphenated_compound_word)
    session.add(
        Waypoint(
            waypoint_type='summit',
            elevation=3715,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Montaña Blanca',
                    description='...',
                    summary='A peak in Tenerife',
                )
            ],
        )
    )
    session.add(
        Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du ciel',
                    description='...',
                    summary='Ski',
                )
            ],
        )
    )
    # a title where the query words appear in a different order,
    # separated by other words (regression fixture, see
    # test_search_multiword_any_order)
    session.add(
        Route(
            activities=['rock_climbing'],
            elevation_max=3000,
            elevation_min=2500,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Gerbier : Traversée des arêtes',
                    description='...',
                    summary='...',
                )
            ],
        )
    )
    # an unrelated title whose stemmed tokens are only one edit away
    # from the stemmed query terms above ("Gerri" -> "geri", one edit
    # from "Gerbier" -> "gerbi") (regression fixture, see
    # test_search_multiword_any_order)
    session.add(
        Route(
            activities=['rock_climbing'],
            elevation_max=3000,
            elevation_min=2500,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Pic de Gerri : arête Noris - Gerri',
                    description='...',
                    summary='...',
                )
            ],
        )
    )
    session.add(
        Route(
            activities=['rock_climbing'],
            elevation_max=1500,
            elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr',
                    title="Vallée d'Ailefroide, Orage d'étoiles, Rivière Kwaï",
                    description='...',
                    summary='...',
                )
            ],
        )
    )
    book1 = Book(
        activities=['hiking'],
        book_types=['biography'],
        locales=[
            DocumentLocale(
                lang='en',
                title="Lac d'Annecy",
                description='...',
                summary="Lac d'Annecy",
            ),
            DocumentLocale(
                lang='en',
                title="Lac d'Annecy",
                description='...',
                summary="Lac d'Annecy",
            ),
        ],
    )
    session.add(book1)
    session.flush()
    fill_index(session)
    # make sure the search index is built
    force_search_index()
    return Docs(article1=article1, waypoint1=waypoint1, book1=book1)


def test_search(client):
    response = client.get(PREFIX + '?q=crolles', status=200)
    body = response.json

    assert 'waypoints' in body
    assert 'routes' in body
    assert 'maps' in body
    assert 'areas' in body
    assert 'articles' in body
    assert 'images' in body
    assert 'outings' in body
    assert 'books' in body

    waypoints = body['waypoints']
    assert waypoints['total'] > 0
    locales = waypoints['documents'][0]['locales']
    assert len(locales) == 2
    assert 'type' in waypoints['documents'][0]

    routes = body['routes']
    assert 0 == routes['total']

    # tests that user results are not included when not authenticated
    assert 'users' not in body


def test_search_by_accented_title_word(client):
    """Single-word queries must match titles containing that exact
    word (regression test for max_expansions being far too low on
    the fuzzy single-word title query, see get_text_query_on_title)."""
    for term in ('Kwaï', 'Rivière'):
        response = client.get(PREFIX + '?q=' + quote(term) + '&t=r', status=200)
        body = response.json
        routes = body['routes']
        assert routes['total'] > 0, f'expected a match for {term!r}, got {routes!r}'


def test_search_hyphenated_compound_word(client):
    """A hyphenated query like "Mont-Blanc" must be treated as two
    words, not one (regression test: counting literal spaces made
    "Mont-Blanc" go through the single-word fuzzy/ngram title query,
    where its ngram prefixes ("mont", "blanc") happened to also match
    an unrelated title ("Montaña Blanca") at least as well as the
    real "Mont Blanc", see get_text_query_on_title)."""
    response = client.get(PREFIX + '?q=' + quote('Mont-Blanc') + '&t=w', status=200)
    body = response.json
    waypoints = body['waypoints']
    assert waypoints['total'] > 0
    titles = [doc['locales'][0]['title'] for doc in waypoints['documents']]
    assert 'Mont Blanc' in titles
    assert 'Montaña Blanca' not in titles


def test_search_multiword_any_order(client):
    """Multi-word queries must match titles containing the same words
    in a different order, interleaved with other words (regression
    test: the title query used to require the words to appear in
    essentially the same order via a `phrase` query, see
    get_text_query_on_title)."""
    response = client.get(
        PREFIX + '?q=' + quote('Aretes de Gerbier') + '&t=r', status=200
    )
    body = response.json
    routes = body['routes']
    assert routes['total'] > 0, (
        f'expected a match for "Aretes de Gerbier", got {routes!r}'
    )
    titles = [doc['locales'][0]['title'] for doc in routes['documents']]
    assert 'Pic de Gerri : arête Noris - Gerri' not in titles


def test_search_by_article_title(client, docs):
    response = client.get(
        PREFIX + '?q=' + str(docs.article1.locales[0].title), status=200
    )
    body = response.json
    articles = body['articles']

    assert len(articles) == 2
    assert articles['total'] != 0


def test_search_by_book_title(client, docs):
    response = client.get(PREFIX + '?q=' + str(docs.book1.locales[0].title), status=200)
    body = response.json
    books = body['books']

    assert len(books) == 2
    assert books['total'] != 0


def test_search_lang(client):
    response = client.get(PREFIX + '?q=crolles&pl=fr', status=200)
    body = response.json

    assert 'waypoints' in body
    assert 'routes' in body

    waypoints = body['waypoints']
    assert waypoints['total'] > 0

    locales = waypoints['documents'][0]['locales']
    assert len(locales) == 1


def test_search_lang_finds_other_language(client):
    """Documents that only exist in a language other than the
    preferred one must still be found (#2223).
    """
    response = client.get(PREFIX + '?q=Mont Blanc&pl=fr', status=200)
    body = response.json

    # "Mont Blanc" waypoint only has an 'en' locale
    waypoints = body['waypoints']
    assert waypoints['total'] > 0


def test_search_authenticated(client):
    """Tests that user results are included when authenticated."""
    headers = auth_headers(username='contributor')
    response = client.get(PREFIX + '?q=crolles', headers=headers, status=200)
    body = response.json

    assert 'users' in body
    users = body['users']
    assert 'total' in users


def test_search_user_unauthenticated(client):
    """Tests that user results are not included when not authenticated."""
    response = client.get(PREFIX + '?q=alex&t=u', status=200)
    body = response.json

    assert 'users' not in body


def test_search_limit_types(client):
    response = client.get(PREFIX + '?q=crolles&t=w,r,c,b', status=200)
    body = response.json

    assert 'waypoints' in body
    assert 'routes' in body
    assert 'articles' in body
    assert 'books' in body
    assert 'maps' not in body
    assert 'areas' not in body
    assert 'images' not in body
    assert 'outings' not in body
    assert 'users' not in body


def test_search_by_document_id(client, docs):
    response = client.get(PREFIX + '?q=' + str(docs.waypoint1.document_id), status=200)
    body = response.json

    waypoints = body['waypoints']
    assert len(waypoints['documents']) == 1
    assert waypoints['total'] == 1

    routes = body['routes']
    assert len(routes['documents']) == 0
    assert routes['total'] == 0
