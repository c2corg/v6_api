"""The routes of the partner outings: `partner_routes` and the links of the outings."""

import datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.jobs.partner_routes import upsert_routes
from c2corg_api.models.partner_outing import (
    PartnerOuting,
    PartnerOutingRoute,
    PartnerRoute,
)
from c2corg_api.partners import normalise
from c2corg_api.partners.model import FetchResult, HarvestedRoute
from c2corg_api.tests.jobs.test_harvest_partner_outings import (
    NOW,
    SETTINGS,
    make_adapter,
    only,
    outing,
    run,
    source_row,
)


@pytest.fixture
def db(db_connection):
    """A session whose commits and rollbacks stay in the test's transaction."""
    with Session(db_connection, join_transaction_mode='create_savepoint') as session:
        yield session


def route(external_id='r1', title='Summit, North face', **kwargs):
    return HarvestedRoute(external_id=external_id, title=title, **kwargs)


def store(db, outings, now=NOW):
    job.upsert_outings(db, outings, now)
    count = upsert_routes(db, outings, now)
    db.flush()
    return count


def routes_of(db, source='fake'):
    db.expire_all()
    return {
        r.external_id: r
        for r in db.scalars(select(PartnerRoute).where(PartnerRoute.source == source))
    }


def links(db, source='fake'):
    """Return {outing external id: [route external ids, by position]}."""
    rows = db.execute(
        select(PartnerOuting.external_id, PartnerRoute.external_id)
        .join(PartnerOutingRoute, PartnerOutingRoute.outing_id == PartnerOuting.id)
        .join(PartnerRoute, PartnerRoute.id == PartnerOutingRoute.route_id)
        .where(PartnerOuting.source == source)
        .order_by(PartnerOuting.external_id, PartnerOutingRoute.position)
    )
    result = {}
    for outing_id, route_id in rows:
        result.setdefault(outing_id, []).append(route_id)
    return result


def test_outings_of_one_route_share_it(db):
    count = store(
        db,
        [
            outing('1', routes=(route(url='https://fake.example/r/1'),)),
            outing('2', routes=(route(),)),
            outing('3'),  # no route
        ],
    )
    assert count == 1
    routes = routes_of(db)
    assert list(routes) == ['r1']
    assert routes['r1'].title == 'Summit, North face'
    assert routes['r1'].url == 'https://fake.example/r/1'  # from the first one
    assert links(db) == {'1': ['r1'], '2': ['r1']}


def test_several_routes_keep_their_order(db):
    store(db, [outing('1', routes=(route('b'), route('a'), route('b')))])
    assert links(db) == {'1': ['b', 'a']}


def test_route_columns(db):
    store(
        db,
        [
            outing(
                '1',
                routes=(
                    route(
                        url='https://fake.example/r/1',
                        summit_name='Summit',
                        elevation_max=3001,
                        lon=6.5,
                        lat=45.5,
                        geom_quality='summit',
                    ),
                ),
            )
        ],
    )
    row = routes_of(db)['r1']
    assert (row.summit_name, row.elevation_max, row.geom_quality) == (
        'Summit',
        3001,
        'summit',
    )
    lon, lat = db.execute(
        select(
            func.ST_X(func.ST_Transform(PartnerRoute.geom, 4326)),
            func.ST_Y(func.ST_Transform(PartnerRoute.geom, 4326)),
        ).where(PartnerRoute.id == row.id)
    ).one()
    assert (round(lon, 6), round(lat, 6)) == (6.5, 45.5)
    assert row.first_seen_at is not None and row.fetched_at == NOW


def test_reupsert_updates_and_keeps_what_the_new_sighting_lacks(db):
    store(
        db,
        [
            outing(
                '1',
                routes=(
                    route(
                        url='https://fake.example/r/1',
                        summit_name='Summit',
                        lon=6.5,
                        lat=45.5,
                        geom_quality='start',
                    ),
                ),
            )
        ],
    )
    first = routes_of(db)['r1']
    first_id, first_seen = first.id, first.first_seen_at
    later = NOW + datetime.timedelta(hours=1)
    store(db, [outing('2', routes=(route(title='Renamed'),))], now=later)
    row = routes_of(db)['r1']
    assert (row.id, row.first_seen_at) == (first_id, first_seen)
    assert row.title == 'Renamed'
    assert row.url == 'https://fake.example/r/1'
    assert row.summit_name == 'Summit'
    assert row.geom is not None and row.geom_quality == 'start'
    assert row.fetched_at == later
    assert links(db) == {'1': ['r1'], '2': ['r1']}


def test_the_links_of_an_outing_follow_its_routes(db):
    store(db, [outing('1', routes=(route('a'), route('b')))])
    # the outing names another route: its links are replaced
    store(db, [outing('1', routes=(route('c'),))])
    assert links(db) == {'1': ['c']}
    # it names none this run (its detail page was not read): the links stay
    store(db, [outing('1')])
    assert links(db) == {'1': ['c']}
    # the routes are kept, linked or not
    assert set(routes_of(db)) == {'a', 'b', 'c'}


def test_same_route_id_in_two_sources(db):
    store(
        db,
        [
            outing('1', source='one', routes=(route(title='One'),)),
            outing('1', source='two', routes=(route(title='Two'),)),
        ],
    )
    assert routes_of(db, 'one')['r1'].title == 'One'
    assert routes_of(db, 'two')['r1'].title == 'Two'
    assert links(db, 'one') == {'1': ['r1']} == links(db, 'two')


def test_batches(db, monkeypatch):
    monkeypatch.setattr('c2corg_api.jobs.partner_routes.BATCH_SIZE', 2)
    outings = [
        outing(str(i), routes=(route(f'r{i % 3}'), route(f'x{i}'))) for i in range(5)
    ]
    assert store(db, outings) == 3 + 5
    assert len(links(db)) == 5


def test_deleting_an_outing_deletes_its_links_not_the_route(db):
    store(db, [outing('1', routes=(route(),)), outing('2', routes=(route(),))])
    db.execute(delete(PartnerOuting).where(PartnerOuting.external_id == '1'))
    assert links(db) == {'2': ['r1']}
    assert list(routes_of(db)) == ['r1']


def test_nothing_to_store(db):
    assert upsert_routes(db, [outing('1')], NOW) == 0
    assert upsert_routes(db, [], NOW) == 0


def test_the_run_stores_the_routes(db):
    def fetch(ctx):
        return FetchResult(
            outings=[
                outing('1', routes=(route(),)),
                outing('2', routes=(route(), route('r2'))),
            ]
        )

    run(db, make_adapter(fetch=fetch))
    assert source_row(db).status == 'ok'
    assert links(db) == {'1': ['r1'], '2': ['r1', 'r2']}


def test_normalise_route():
    assert normalise.route(' 12 ', '<b>Pic</b>  Nord', url='') == HarvestedRoute(
        external_id='12', title='Pic Nord'
    )
    assert normalise.route(None, 'Pic') is None
    assert normalise.route('12', ' ') is None
    assert normalise.route('x' * 129, 'Pic') is None
    odd = normalise.route('1', 'Pic', elevation_max='9500', lon=0, lat=0)
    assert (odd.elevation_max, odd.lon, odd.geom_quality) == (None, None, 'none')
    ok = normalise.route(
        '1', 'Pic', elevation_max='2500', lon=6.5, lat=45.5, geom_quality='start'
    )
    assert (ok.elevation_max, ok.lon, ok.lat, ok.geom_quality) == (
        2500,
        6.5,
        45.5,
        'start',
    )


def test_fixture_mode_with_the_real_adapters_stores_their_routes(db, db_connection):
    settings = {
        **SETTINGS,
        **only('skitour', 'gulliver', 'bivouak', 'gipfelbuch'),
        'partners.transport': 'fixtures',
    }
    job.harvest_partner_outings(settings, now=NOW)
    counts = {}
    for name in ('skitour', 'gulliver', 'bivouak', 'gipfelbuch'):
        linked = links(db, name)
        outings = db.scalar(
            select(func.count())
            .select_from(PartnerOuting)
            .where(PartnerOuting.source == name)
        )
        counts[name] = (outings, len(linked), len(routes_of(db, name)))
    # skitour: 21 of the 30 outings link a topo, 22 topos (one outing links
    # three, one two; two topos are shared)
    assert counts['skitour'] == (30, 21, 22)
    gulliver_outings, gulliver_linked, gulliver_routes = counts['gulliver']
    # every gulliver report has its route, some routes have several reports
    assert gulliver_linked == gulliver_outings
    assert gulliver_routes < gulliver_outings
    # bivouak: the outings whose detail page names a topo
    assert counts['bivouak'][1] > 0
    assert counts['bivouak'][2] == counts['bivouak'][1]
    gipfelbuch_outings, gipfelbuch_linked, gipfelbuch_routes = counts['gipfelbuch']
    assert gipfelbuch_linked == gipfelbuch_outings
    assert 0 < gipfelbuch_routes <= gipfelbuch_outings
    assert links(db, 'skitour')['188886'] == ['198', '812', '9136']
    topo = routes_of(db, 'skitour')['215']
    assert (topo.title, topo.url) == (
        'Croix de Chamrousse, par les pistes',
        'https://skitour.fr/topos/215',
    )
