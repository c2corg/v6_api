"""GET /partner-outings (partner rows merged with the c2c outings) and /sources."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.partner_outing import (
    PartnerOuting,
    PartnerOutingRoute,
    PartnerRoute,
    PartnerSource,
)
from c2corg_api.models.user import User

TODAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    # the default window is 2026-11-11..2026-11-24
    monkeypatch.setattr('c2corg_api.views.partner_outings.today', lambda: TODAY)


@dataclass
class Data:
    """The ids of the rows of `data`."""

    area_range: int
    area_country: int
    c1: int
    c2: int
    c3: int
    c4: int
    c_redirect: int
    c_empty: int
    c_old: int
    outing_user: str


def _outing(session, title_by_lang, day, geom=None, **fields):
    outing = Outing(
        activities=fields.pop('activities', ['skitouring']),
        date_start=day,
        date_end=day,
        locales=[
            OutingLocale(lang=lang, title=title)
            for lang, title in title_by_lang.items()
        ],
        **fields,
    )
    if geom:
        outing.geometry = DocumentGeometry(geom=f'SRID=3857;POINT({geom})')
    session.add(outing)
    session.flush()
    return outing.document_id


def _partner(session, source, external_id, day, **fields):
    session.add(
        PartnerOuting(
            source=source,
            external_id=external_id,
            url=f'https://{source}.example/{external_id}',
            title=fields.pop('title', f'{source} {external_id}'),
            date=day,
            activities=fields.pop('activities', ['skitouring']),
            **fields,
        )
    )


@pytest.fixture
def data(session, user_ids) -> Data:
    range_area = Area(
        area_type='range',
        locales=[
            DocumentLocale(lang='fr', title='Belledonne'),
            DocumentLocale(lang='en', title='Belledonne Range'),
        ],
    )
    country = Area(
        area_type='country', locales=[DocumentLocale(lang='fr', title='France')]
    )
    session.add_all([range_area, country])
    session.flush()
    area_a, area_b = range_area.document_id, country.document_id

    # c2c outings
    c1 = _outing(
        session,
        {'en': 'C1 en', 'it': 'C1 it'},
        date(2026, 11, 20),
        '100 100',
        ski_rating='3.2',
        height_diff_up=900,
        elevation_max=2500,
    )
    c2 = _outing(
        session, {'fr': 'C2 fr'}, date(2026, 11, 22), '5000 5000', ski_rating='4.2'
    )
    c3 = _outing(
        session,
        {'fr': 'C3 fr'},
        date(2026, 11, 22),
        activities=['hiking'],
        labande_global_rating='D',
    )
    c4 = _outing(
        session, {'fr': 'C4 fr'}, date(2026, 11, 18), '300 300', ski_rating='2.1'
    )
    c_empty = _outing(session, {'fr': 'empty'}, date(2026, 11, 22), quality='empty')
    c_old = _outing(session, {'fr': 'old'}, date(2026, 9, 1))
    c_redirect = _outing(
        session, {'fr': 'redirect'}, date(2026, 11, 22), redirects_to=c1
    )
    session.add_all(
        [
            AreaAssociation(document_id=c1, area_id=area_a),
            AreaAssociation(document_id=c1, area_id=area_b),
            AreaAssociation(document_id=c2, area_id=area_b),
        ]
    )
    # the author is the associated user with the lowest id
    first, second = sorted(
        (user_ids['contributor'], user_ids['contributor2']),
    )
    for user_id in (second, first):
        session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type='u',
                child_document_id=c1,
                child_document_type='o',
            )
        )
    session.flush()
    author = session.query(User.name).filter(User.id == first).scalar()

    # partner outings
    _partner(
        session,
        'skitour',
        'ext1',
        date(2026, 11, 22),
        title='P1 Etendard',
        lang='fr',
        author='jdoe',
        author_url='https://skitour.example/u/jdoe',
        region='Grandes Rousses',
        ski_rating_min='3.2',
        ski_rating_max='3.2',
        rating_raw='3.2',
        rating_system='c2c_ski',
        orientations=['N', 'NE'],
        elevation_max=3464,
        height_diff_up=1500,
        geom='SRID=3857;POINT(110 110)',
        geom_quality='summit',
        area_ids=[area_a],
        snow={'top_cm': 40},
        gpx_url='https://skitour.example/ext1.gpx',
        texts={'narrative': 'SECRET-NARRATIVE', 'conditions': 'SECRET-CONDITIONS'},
    )
    _partner(
        session,
        'skitour',
        'ext2',
        date(2026, 11, 22),
        ski_rating_min='4.1',
        ski_rating_max='4.1',
        rating_raw='4.1',
        rating_system='c2c_ski',
        steep=True,
        geom='SRID=3857;POINT(9000 9000)',
        geom_quality='summit',
        area_ids=[area_b],
    )
    _partner(
        session,
        'gulliver',
        'g1',
        date(2026, 11, 22),
        lang='it',
        ski_rating_min='2.1',
        ski_rating_max='3.3',
        rating_raw='BS',
        rating_system='blachere',
        source_activity='skimo',
    )
    _partner(
        session,
        'gulliver',
        'g2',
        date(2026, 11, 20),
        activities=['snowshoeing'],
        geom='SRID=3857;POINT(200 200)',
        geom_quality='start',
    )
    _partner(session, 'skitour', 'old', date(2026, 9, 1))
    session.flush()
    return Data(area_a, area_b, c1, c2, c3, c4, c_redirect, c_empty, c_old, author)


C2C_ORDER = ['c1', 'c2', 'c3', 'c4']


def ids(response):
    return [item['id'] for item in response.json['items']]


def c2c_id(document_id):
    return f'c2c:{document_id}'


def listing(client, **params):
    return client.get('/partner-outings', params=params, status=200)


# the default window, in the order of the answer: the day desc, the source,
# the id
@pytest.fixture
def default_order(data):
    return [
        c2c_id(data.c2),
        c2c_id(data.c3),
        'gulliver:g1',
        'skitour:ext1',
        'skitour:ext2',
        c2c_id(data.c1),
        'gulliver:g2',
        c2c_id(data.c4),
    ]


class TestMerge:
    def test_default_window_and_order(self, client, data, default_order):
        # the window drops the old outings, the redirect and the empty outing
        response = listing(client)
        assert ids(response) == default_order
        assert response.json['total'] == 8

    def test_union_total_and_paging(self, client, data, default_order):
        response = listing(client, limit=3, offset=2)
        assert ids(response) == default_order[2:5]
        assert response.json['total'] == 8
        response = listing(client, limit=3, offset=6)
        assert ids(response) == default_order[6:]
        assert response.json['total'] == 8
        response = listing(client, offset=50)
        assert ids(response) == []
        assert response.json['total'] == 8

    def test_pages_do_not_overlap(self, client, data, default_order):
        seen = []
        for offset in range(0, 8, 2):
            seen += ids(listing(client, limit=2, offset=offset))
        assert seen == default_order

    def test_sources_only(self, client, data):
        assert ids(listing(client, sources='c2c')) == [
            c2c_id(data.c2),
            c2c_id(data.c3),
            c2c_id(data.c1),
            c2c_id(data.c4),
        ]
        response = listing(client, sources='skitour')
        assert ids(response) == ['skitour:ext1', 'skitour:ext2']
        assert response.json['total'] == 2
        assert ids(listing(client, sources='gulliver')) == [
            'gulliver:g1',
            'gulliver:g2',
        ]
        assert ids(listing(client, sources='gulliver,c2c')) == [
            c2c_id(data.c2),
            c2c_id(data.c3),
            'gulliver:g1',
            c2c_id(data.c1),
            'gulliver:g2',
            c2c_id(data.c4),
        ]

    def test_partner_only_filters_drop_c2c_rows(self, client, data):
        # the c2c outings without a rating or a position match no rating or
        # bbox filter; `sources` drops them all
        assert c2c_id(data.c3) not in ids(listing(client, trat='1.1,5.6'))
        assert c2c_id(data.c3) not in ids(listing(client, bbox='-1,-1,1e7,1e7'))
        assert c2c_id(data.c3) in ids(listing(client, act='hiking'))
        assert not any(
            i.startswith('c2c:') for i in ids(listing(client, sources='skitour'))
        )


class TestFilters:
    def test_area(self, client, data):
        assert ids(listing(client, a=data.area_range)) == [
            'skitour:ext1',
            c2c_id(data.c1),
        ]
        assert ids(listing(client, a=data.area_country)) == [
            c2c_id(data.c2),
            'skitour:ext2',
            c2c_id(data.c1),
        ]
        both = listing(client, a=f'{data.area_range},{data.area_country}')
        assert both.json['total'] == 4
        assert ids(listing(client, a=999999)) == []

    def test_bbox(self, client, data):
        # EPSG:3857
        assert ids(listing(client, bbox='0,0,1000,1000')) == [
            'skitour:ext1',
            c2c_id(data.c1),
            'gulliver:g2',
            c2c_id(data.c4),
        ]
        assert ids(listing(client, bbox='4000,4000,10000,10000')) == [
            c2c_id(data.c2),
            'skitour:ext2',
        ]
        assert ids(listing(client, bbox='-5,-5,-1,-1')) == []

    def test_date(self, client, data):
        assert ids(listing(client, date='2026-11-22')) == [
            c2c_id(data.c2),
            c2c_id(data.c3),
            'gulliver:g1',
            'skitour:ext1',
            'skitour:ext2',
        ]
        assert ids(listing(client, date='2026-11-18,2026-11-20')) == [
            c2c_id(data.c1),
            'gulliver:g2',
            c2c_id(data.c4),
        ]
        # outside of the default window
        assert ids(listing(client, date='2026-09-01')) == [
            c2c_id(data.c_old),
            'skitour:old',
        ]
        assert ids(listing(client, date='2026-11-19')) == []

    def test_date_limits_are_included(self, client, data):
        assert ids(listing(client, date='2026-11-20,2026-11-20')) == [
            c2c_id(data.c1),
            'gulliver:g2',
        ]
        # 31 days at most
        assert listing(client, date='2026-10-22,2026-11-22').json['total'] == 8

    def test_activities(self, client, data):
        assert ids(listing(client, act='snowshoeing')) == ['gulliver:g2']
        assert ids(listing(client, act='hiking')) == [c2c_id(data.c3)]
        assert listing(client, act='skitouring').json['total'] == 6
        assert listing(client, act='hiking,snowshoeing').json['total'] == 2

    def test_rating_overlap(self, client, data):
        # a Blachere interval (2.1..3.3) matches a query inside it, and the
        # exact ratings of the others; no rating: no match
        assert ids(listing(client, trat='3.1,3.3')) == [
            'gulliver:g1',
            'skitour:ext1',
            c2c_id(data.c1),
        ]
        assert ids(listing(client, trat='2.2,2.3')) == ['gulliver:g1']
        assert ids(listing(client, trat='4.1,')) == [
            c2c_id(data.c2),
            'skitour:ext2',
        ]
        assert ids(listing(client, trat=',2.1')) == [
            'gulliver:g1',
            c2c_id(data.c4),
        ]
        assert ids(listing(client, trat='4.2,4.2')) == [c2c_id(data.c2)]
        # the touching bounds count
        assert ids(listing(client, trat='3.3,4.1')) == [
            'gulliver:g1',
            'skitour:ext2',
        ]
        assert ids(listing(client, trat='5.1,5.6')) == []

    def test_steep(self, client, data):
        # the c2c rows: ski rating from 4.1 or global rating from D-
        assert ids(listing(client, steep='true')) == [
            c2c_id(data.c2),
            c2c_id(data.c3),
            'skitour:ext2',
        ]
        assert ids(listing(client, steep='1')) == ids(listing(client, steep='true'))
        assert ids(listing(client, steep='false')) == [
            'gulliver:g1',
            'skitour:ext1',
            c2c_id(data.c1),
            'gulliver:g2',
            c2c_id(data.c4),
        ]
        assert ids(listing(client, steep='0')) == ids(listing(client, steep='false'))

    def test_steep_flag_of_the_items(self, client, data):
        steep = {i['id']: i['steep'] for i in listing(client).json['items']}
        assert steep[c2c_id(data.c2)] is True
        assert steep[c2c_id(data.c3)] is True
        assert steep[c2c_id(data.c1)] is False
        assert steep['skitour:ext2'] is True
        assert steep['skitour:ext1'] is False

    def test_combined(self, client, data):
        assert ids(
            listing(
                client,
                act='skitouring',
                steep='true',
                a=data.area_country,
            )
        ) == [c2c_id(data.c2), 'skitour:ext2']
        assert ids(
            listing(
                client,
                act='skitouring',
                steep='true',
                a=data.area_country,
                sources='c2c',
            )
        ) == [c2c_id(data.c2)]
        assert ids(
            listing(
                client,
                bbox='0,0,1000,1000',
                date='2026-11-20,2026-11-22',
                trat='3.1,3.3',
            )
        ) == ['skitour:ext1', c2c_id(data.c1)]
        assert ids(
            listing(
                client,
                bbox='0,0,1000,1000',
                sources='skitour',
                trat='3.1,3.3',
                limit=1,
            )
        ) == ['skitour:ext1']
        # nothing matches both
        assert listing(client, act='hiking', steep='false').json['total'] == 0
        response = listing(client, act='hiking', steep='true', limit=1, offset=0)
        assert response.json['total'] == 1


class TestItems:
    def test_c2c_item(self, client, data):
        item = next(
            i
            for i in listing(client, pl='en').json['items']
            if i['id'] == c2c_id(data.c1)
        )
        assert item == {
            'id': c2c_id(data.c1),
            'source': 'c2c',
            'document_id': data.c1,
            'url': None,
            'title': 'C1 en',
            'lang': 'en',
            'date': '2026-11-20',
            'author': {'name': data.outing_user, 'url': None},
            'activities': ['skitouring'],
            'source_activity': None,
            'rating': {
                'ski_rating_min': '3.2',
                'ski_rating_max': '3.2',
                'raw': '3.2',
                'system': 'c2c_ski',
            },
            'steep': False,
            'elevation_max': 2500,
            'height_diff_up': 900,
            'orientations': [],
            'snow': None,
            'gpx_url': None,
            'has_track': False,
            'routes': [],
            'region': None,
            'geometry': {
                'geom': '{"type":"Point","coordinates":[100,100]}',
                'quality': 'start',
            },
            'areas': [
                {
                    'document_id': data.area_range,
                    'area_type': 'range',
                    'title': 'Belledonne Range',
                },
                {
                    'document_id': data.area_country,
                    'area_type': 'country',
                    'title': 'France',
                },
            ],
            'credit': {
                'site': 'camptocamp.org',
                'site_url': 'https://www.camptocamp.org',
            },
        }

    def test_partner_routes(self, client, data, session):
        def outing_id(external_id):
            return (
                session.query(PartnerOuting.id)
                .filter_by(source='skitour', external_id=external_id)
                .scalar()
            )

        main = PartnerRoute(
            source='skitour',
            external_id='12',
            title='Etendard, Combe NE',
            url='https://skitour.example/topos/12',
        )
        other = PartnerRoute(source='skitour', external_id='13', title='Col, S')
        session.add_all([main, other])
        session.flush()
        session.add_all(
            [
                PartnerOutingRoute(
                    outing_id=outing_id('ext1'), route_id=other.id, position=1
                ),
                PartnerOutingRoute(
                    outing_id=outing_id('ext1'), route_id=main.id, position=0
                ),
                PartnerOutingRoute(outing_id=outing_id('ext2'), route_id=main.id),
            ]
        )
        session.flush()
        items = {i['id']: i for i in listing(client).json['items']}
        # the main route first; one route can have several outings
        assert items['skitour:ext1']['routes'] == [
            {'title': 'Etendard, Combe NE', 'url': 'https://skitour.example/topos/12'},
            {'title': 'Col, S', 'url': None},
        ]
        assert items['skitour:ext2']['routes'] == [
            {'title': 'Etendard, Combe NE', 'url': 'https://skitour.example/topos/12'}
        ]
        assert items['gulliver:g1']['routes'] == []
        assert items[c2c_id(data.c1)]['routes'] == []

    def test_c2c_titles_use_the_best_locale(self, client, data):
        def title(**params):
            items = listing(client, sources='c2c', **params).json['items']
            return next(i for i in items if i['document_id'] == data.c1)

        # the langs priority without pl (fr, en, it...), pl first otherwise
        assert title()['title'] == 'C1 en'
        assert title(pl='it')['title'] == 'C1 it'
        assert title(pl='it')['lang'] == 'it'
        # not in this language: the best other one
        assert title(pl='de')['title'] == 'C1 en'
        # the same rule names the areas
        assert [a['title'] for a in title()['areas']] == ['Belledonne', 'France']
        assert [a['title'] for a in title(pl='en')['areas']] == [
            'Belledonne Range',
            'France',
        ]

    def test_c2c_without_author_geometry_rating(self, client, data):
        items = {i['id']: i for i in listing(client).json['items']}
        c3 = items[c2c_id(data.c3)]
        assert c3['author'] is None
        assert c3['geometry'] is None
        assert c3['rating'] is None
        assert c3['areas'] == []
        assert c3['title'] == 'C3 fr'

    def test_partner_item(self, client, data):
        item = next(
            i for i in listing(client).json['items'] if i['id'] == 'skitour:ext1'
        )
        assert item == {
            'id': 'skitour:ext1',
            'source': 'skitour',
            'document_id': None,
            'url': 'https://skitour.example/ext1',
            'title': 'P1 Etendard',
            'lang': 'fr',
            'date': '2026-11-22',
            'author': {'name': 'jdoe', 'url': 'https://skitour.example/u/jdoe'},
            'activities': ['skitouring'],
            'source_activity': None,
            'rating': {
                'ski_rating_min': '3.2',
                'ski_rating_max': '3.2',
                'raw': '3.2',
                'system': 'c2c_ski',
            },
            'steep': False,
            'elevation_max': 3464,
            'height_diff_up': 1500,
            'orientations': ['N', 'NE'],
            'snow': {'top_cm': 40},
            'gpx_url': 'https://skitour.example/ext1.gpx',
            'has_track': False,
            'routes': [],
            'region': 'Grandes Rousses',
            'geometry': {
                'geom': '{"type":"Point","coordinates":[110,110]}',
                'quality': 'summit',
            },
            'areas': [
                {
                    'document_id': data.area_range,
                    'area_type': 'range',
                    'title': 'Belledonne',
                }
            ],
            'credit': {'site': 'skitour.fr', 'site_url': 'https://skitour.fr'},
        }

    def test_texts_are_never_served(self, client, data):
        """The partner texts are stored (`texts`), never in an answer."""
        for params in ({}, {'sources': 'skitour'}, {'limit': 1}):
            response = listing(client, **params)
            assert 'SECRET-' not in response.text
            assert all('texts' not in item for item in response.json['items'])
        sources = client.get('/partner-outings/sources', status=200)
        assert 'SECRET-' not in sources.text

    def test_partner_area_titles_follow_pl(self, client, data):
        for pl, title in (('en', 'Belledonne Range'), ('fr', 'Belledonne')):
            items = listing(client, pl=pl, sources='skitour').json['items']
            assert items[0]['areas'][0]['title'] == title

    def test_partner_item_without_author_nor_position(self, client, data):
        item = next(
            i for i in listing(client).json['items'] if i['id'] == 'gulliver:g1'
        )
        assert item['author'] is None
        assert item['geometry'] is None
        assert item['areas'] == []
        assert item['rating']['system'] == 'blachere'
        assert item['rating']['raw'] == 'BS'
        assert item['source_activity'] == 'skimo'
        assert item['orientations'] == []

    def test_credit_on_every_item(self, client, data):
        items = listing(client).json['items']
        assert len(items) == 8
        credits = {i['source']: i['credit'] for i in items}
        assert credits == {
            'c2c': {'site': 'camptocamp.org', 'site_url': 'https://www.camptocamp.org'},
            'skitour': {'site': 'skitour.fr', 'site_url': 'https://skitour.fr'},
            'gulliver': {'site': 'gulliver.it', 'site_url': 'https://www.gulliver.it'},
        }
        for item in items:
            assert item['credit']['site'] and item['credit']['site_url']

    def test_unknown_source_is_credited_by_its_name(self, client, session, data):
        _partner(session, 'newsite', 'x1', date(2026, 11, 23))
        session.flush()
        item = next(
            i for i in listing(client).json['items'] if i['source'] == 'newsite'
        )
        assert item['credit'] == {'site': 'newsite', 'site_url': ''}


def test_credits_come_from_the_adapters():
    from c2corg_api.partners.sources import REGISTRY
    from c2corg_api.views import partner_outings as view

    assert set(view.SITES) == {view.C2C, *REGISTRY}
    for name, adapter in REGISTRY.items():
        assert view._credit(name) == {
            'site': adapter.site_name,
            'site_url': adapter.site_url,
        }
    assert view._credit(view.C2C)['site'] == 'camptocamp.org'


class TestSources:
    def test_health_in_the_listing(self, client, session, data):
        session.add(
            PartnerSource(
                source='skitour',
                status='ok',
                last_success_at=datetime(2026, 11, 24, 10, 15, tzinfo=UTC),
            )
        )
        session.flush()
        assert listing(client).json['sources'] == [
            {'source': 'bivouak', 'status': 'never_run', 'last_success_at': None},
            {'source': 'gipfelbuch', 'status': 'never_run', 'last_success_at': None},
            {'source': 'gulliver', 'status': 'never_run', 'last_success_at': None},
            {
                'source': 'onice',
                'status': 'never_run',
                'last_success_at': None,
            },
            {
                'source': 'skitour',
                'status': 'ok',
                'last_success_at': '2026-11-24T10:15:00+00:00',
            },
            {
                'source': 'skitourenportal',
                'status': 'never_run',
                'last_success_at': None,
            },
        ]

    def test_unconfigured_source_is_listed_as_disabled(self, client, session):
        session.add(
            PartnerSource(
                source='gulliver', status='disabled', status_detail='not configured'
            )
        )
        session.flush()
        sources = client.get('/partner-outings/sources', status=200).json['sources']
        by_name = {s['source']: s for s in sources}
        assert by_name['gulliver']['status'] == 'disabled'
        assert by_name['gulliver']['status_detail'] == 'not configured'
        assert by_name['skitour']['status'] == 'never_run'

    def test_sources_route(self, client, session):
        session.add(
            PartnerSource(
                source='gulliver',
                status='blocked',
                status_detail='HTTP 403 Cloudflare challenge',
                last_run_at=datetime(2026, 11, 24, 9, 0, tzinfo=UTC),
                last_fetched=0,
                last_skipped={'parse_error': 1},
                cursor={'secret': 'cursor-value'},  # nosec B105 (a fake cursor)
            )
        )
        session.flush()
        response = client.get('/partner-outings/sources', status=200)
        assert response.json == {
            'sources': [
                {
                    'source': 'bivouak',
                    'site_name': 'bivouak.net',
                    'site_url': 'https://www.bivouak.net',
                    'status': 'never_run',
                    'status_detail': None,
                    'last_success_at': None,
                    'last_run_at': None,
                    'last_fetched': None,
                    'last_skipped': {},
                },
                {
                    'source': 'gipfelbuch',
                    'site_name': 'gipfelbuch.ch',
                    'site_url': 'https://www.gipfelbuch.ch',
                    'status': 'never_run',
                    'status_detail': None,
                    'last_success_at': None,
                    'last_run_at': None,
                    'last_fetched': None,
                    'last_skipped': {},
                },
                {
                    'source': 'gulliver',
                    'site_name': 'gulliver.it',
                    'site_url': 'https://www.gulliver.it',
                    'status': 'blocked',
                    'status_detail': 'HTTP 403 Cloudflare challenge',
                    'last_success_at': None,
                    'last_run_at': '2026-11-24T09:00:00+00:00',
                    'last_fetched': 0,
                    'last_skipped': {'parse_error': 1},
                },
                {
                    'source': 'onice',
                    'site_name': 'on-ice.it',
                    'site_url': 'http://www.on-ice.it/onice/',
                    'status': 'never_run',
                    'status_detail': None,
                    'last_success_at': None,
                    'last_run_at': None,
                    'last_fetched': None,
                    'last_skipped': {},
                },
                {
                    'source': 'skitour',
                    'site_name': 'skitour.fr',
                    'site_url': 'https://skitour.fr',
                    'status': 'never_run',
                    'status_detail': None,
                    'last_success_at': None,
                    'last_run_at': None,
                    'last_fetched': None,
                    'last_skipped': {},
                },
                {
                    'source': 'skitourenportal',
                    'site_name': 'skitourenportal.eu',
                    'site_url': 'https://skitourenportal.eu',
                    'status': 'never_run',
                    'status_detail': None,
                    'last_success_at': None,
                    'last_run_at': None,
                    'last_fetched': None,
                    'last_skipped': {},
                },
            ]
        }
        assert 'cursor' not in response.text
        assert 'cursor-value' not in response.text


class TestRequest:
    def test_head(self, client, data):
        response = client.head('/partner-outings', status=200)
        assert response.headers['Cache-Control'] == 'public, max-age=120'
        client.head('/partner-outings/sources', status=200)

    def test_cache_control(self, client, data):
        response = client.get('/partner-outings', status=200)
        assert response.headers['Cache-Control'] == 'public, max-age=120'

    def test_empty_database(self, client):
        response = listing(client)
        assert response.json['total'] == 0
        assert response.json['items'] == []

    @pytest.mark.parametrize(
        ('name', 'value'),
        [
            ('a', 'x'),
            ('a', '1,,2'),
            ('a', '-1'),
            ('bbox', '1,2,3'),
            ('bbox', '1,2,3,x'),
            ('bbox', '1,2,3,nan'),
            ('bbox', '1,2,3,inf'),
            ('bbox', '5,0,1,1'),
            ('date', '2026-13-01'),
            ('date', 'yesterday'),
            ('date', '2026-11-22,2026-11-20'),
            ('date', '2026-10-01,2026-11-22'),
            ('date', '2026-11-01,2026-11-02,2026-11-03'),
            ('act', 'swimming'),
            ('act', 'skitouring,'),
            ('trat', '9.9,'),
            ('trat', ','),
            ('trat', '3.1'),
            ('trat', '4.1,3.1'),
            ('steep', 'maybe'),
            ('sources', 'nowhere'),
            ('sources', 'skitour,'),
            ('pl', 'xx'),
            ('limit', '0'),
            ('limit', '301'),
            ('limit', 'x'),
            ('offset', '-1'),
            ('offset', 'x'),
        ],
    )
    def test_invalid_parameters(self, client, name, value):
        response = client.get('/partner-outings', params={name: value}, status=400)
        assert response.json == {
            'status': 'error',
            'errors': [
                {
                    'location': 'querystring',
                    'name': name,
                    'description': f'invalid {name}',
                }
            ],
        }

    def test_empty_parameters_are_not_given(self, client, data, default_order):
        response = listing(client, a='', act='', trat='', steep='', sources='')
        assert ids(response) == default_order

    def test_cached_for_the_same_parameters(self, client, session, data):
        first = listing(client, limit=2).json
        _partner(session, 'skitour', 'late', date(2026, 11, 23))
        session.flush()
        # the same normalised query: the cached answer
        assert listing(client, limit='2').json == first
        # another query is not
        assert listing(client, limit=3).json['total'] == 9


class TestSql:
    def test_no_newer_than_postgresql_9_6(self):
        # a guard on what the SQL is written with: no generated columns, no
        # functions or syntax of PostgreSQL 10 and later
        import inspect

        from c2corg_api.views import partner_outings

        source = inspect.getsource(partner_outings).lower()
        for newer in (
            'generated',
            'jsonb_path',
            'websearch_to_tsquery',
            'string_to_table',
            'starts_with(',
            'cardinality(',
            'on conflict do select',
            'merge into',
        ):
            assert newer not in source, newer
