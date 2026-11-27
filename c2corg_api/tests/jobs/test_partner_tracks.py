"""The second phase of a harvest run: the GPX tracks, and how the API serves them."""

import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.jobs import partner_tracks as tracks
from c2corg_api.models.partner_outing import PartnerOuting, PartnerTrack
from c2corg_api.partners.adapter import SourceBlocked, SourceDown
from c2corg_api.partners.model import HarvestedOuting, RateLimit
from c2corg_api.partners.sources.gulliver import GulliverAdapter
from c2corg_api.partners.sources.skitour import SkitourAdapter
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
FIXTURES = Path(__file__).parent.parent / 'partners' / 'fixtures'
GPX = 'https://www.gulliver.it/wp-content/uploads/2026/11/'
MONTECRESTESE = GPX + 'AnelloBorgateMontecrestese.gpx'
VALTOURNENCHE = GPX + '2026-11-22-10-05-42.gpx'
SETTINGS = {
    'partners.transport': 'fixtures',
    'partners.allow_synthetic': 'true',
    'partners.tracks_per_run': '3',
}
LINE = (
    b'<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk>'
    b'<trkseg><trkpt lat="45.1" lon="7.1"/><trkpt lat="45.2" lon="7.2"/></trkseg>'
    b'</trk></gpx>'
)


@pytest.fixture
def db(db_connection):
    with Session(db_connection, join_transaction_mode='create_savepoint') as session:
        yield session


def outing(external_id, gpx_url, days_ago=1, author='user1'):
    return HarvestedOuting(
        source='gulliver',
        external_id=external_id,
        url=f'https://www.gulliver.it/itinerari/x/2026/11/26/{external_id}/',
        title=f'Gita {external_id}',
        date=TODAY - datetime.timedelta(days=days_ago),
        activities=('hiking',),
        author=author,
        gpx_url=gpx_url,
    )


class Answers:
    """A transport answering each URL from a dict (a response or an exception)."""

    def __init__(self, answers, budget=3):
        self.answers = answers
        self.rate = RateLimit(10.0, budget, 30)
        self.calls = []

    @property
    def request_count(self):
        return len(self.calls)

    def get(self, url, *, params=None, headers=None):
        self.calls.append(url)
        answer = self.answers.get(url, LINE)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return HttpResponse(answer, {}, b'', url)
        return HttpResponse(200, {}, answer, url)


def stored(db):
    db.expire_all()
    return {t.external_id: t for t in db.scalars(select(PartnerTrack))}


def run(db, transport, now=NOW):
    return tracks.harvest_tracks(db, GulliverAdapter, transport, now, SETTINGS)


def test_settings_and_transport(tmp_path):
    assert tracks.tracks_per_run({}) == 3
    assert tracks.tracks_per_run({'partners.tracks_per_run': '0'}) == 0
    assert tracks._interval({'partners.tracks_interval_seconds': '1'}) == 10.0
    assert tracks._interval({'partners.tracks_interval_seconds': '30'}) == 30.0
    http = tracks.track_transport(GulliverAdapter, {'partners.transport': 'http'})
    assert http.max_bytes == tracks.gpx.MAX_BYTES
    assert (http.rate.min_interval_s, http.rate.max_requests_per_run) == (10.0, 3)
    # only the sources with a licence for their tracks
    assert tracks.track_transport(SkitourAdapter, SETTINGS, FIXTURES) is None
    off = {**SETTINGS, 'partners.tracks_per_run': '0'}
    assert tracks.track_transport(GulliverAdapter, off, FIXTURES) is None
    fixtures = tracks.track_transport(GulliverAdapter, SETTINGS, FIXTURES)
    assert isinstance(fixtures, FixtureTransport)
    # the track fixtures are synthetic
    strict = {**SETTINGS, 'partners.allow_synthetic': 'false'}
    assert tracks.track_transport(GulliverAdapter, strict, FIXTURES) is None
    assert tracks.track_transport(GulliverAdapter, SETTINGS, tmp_path) is None


def test_newest_first_within_the_budget(db):
    job.upsert_outings(
        db,
        [
            outing('1', GPX + 'a.gpx', days_ago=5),
            outing('2', GPX + 'b.gpx', days_ago=1),
            outing('3', None),
            outing('4', GPX + 'c.gpx', days_ago=3),
        ],
        NOW,
    )
    transport = Answers({}, budget=2)
    assert run(db, transport) == {'ok': 2, 'failed': 0, 'invalid': 0}
    assert transport.calls == [GPX + 'b.gpx', GPX + 'c.gpx']
    rows = stored(db)
    assert set(rows) == {'2', '4'}
    assert rows['2'].status == 'ok'
    assert rows['2'].point_count == 2
    assert rows['2'].attempts == 1
    # the next run takes the next one, never the same file again
    transport = Answers({}, budget=2)
    run(db, transport, NOW + datetime.timedelta(minutes=15))
    assert transport.calls == [GPX + 'a.gpx']


def test_failures_are_retried_later_then_given_up(db):
    job.upsert_outings(db, [outing('1', GPX + 'a.gpx')], NOW)
    down = Answers({GPX + 'a.gpx': SourceDown('timeout')})
    assert run(db, down)['failed'] == 1
    track = stored(db)['1']
    assert (track.status, track.attempts, track.detail) == ('failed', 1, 'timeout')
    # not before 1 hour, then 2, 4: at most MAX_ATTEMPTS attempts
    now = NOW
    for attempts in range(1, tracks.MAX_ATTEMPTS):
        soon = Answers({GPX + 'a.gpx': SourceDown('timeout')})
        run(db, soon, now + datetime.timedelta(minutes=30))
        assert soon.calls == []
        now += tracks.retry_delay(attempts) + datetime.timedelta(minutes=1)
        later = Answers({GPX + 'a.gpx': SourceDown('timeout')})
        run(db, later, now)
        assert later.calls == [GPX + 'a.gpx']
    assert stored(db)['1'].attempts == tracks.MAX_ATTEMPTS
    never = Answers({})
    run(db, never, now + datetime.timedelta(days=30))
    assert never.calls == []


def test_a_new_file_is_read_again(db):
    job.upsert_outings(db, [outing('1', GPX + 'a.gpx')], NOW)
    run(db, Answers({GPX + 'a.gpx': b'<gpx/>'}))
    assert stored(db)['1'].status == 'invalid'
    assert run(db, Answers({})) == {'ok': 0, 'failed': 0, 'invalid': 0}
    # the report links to another file
    job.upsert_outings(db, [outing('1', GPX + 'b.gpx')], NOW)
    run(db, Answers({}))
    track = stored(db)['1']
    assert (track.status, track.gpx_url, track.attempts) == ('ok', GPX + 'b.gpx', 1)


@pytest.mark.parametrize(
    ('answer', 'detail'),
    [
        (404, 'HTTP 404'),
        (b'<html>not a gpx</html>', 'not a GPX file'),
        (b'x' * (tracks.gpx.MAX_BYTES + 1), 'too large'),
        (b'<!DOCTYPE gpx [<!ENTITY x SYSTEM "file:///etc/passwd">]><gpx/>', 'refused'),
    ],
)
def test_invalid_files(db, answer, detail):
    job.upsert_outings(db, [outing('1', GPX + 'a.gpx')], NOW)
    assert run(db, Answers({GPX + 'a.gpx': answer}))['invalid'] == 1
    track = stored(db)['1']
    assert track.status == 'invalid'
    assert detail in track.detail
    assert track.geom is None


def test_a_block_stops_the_phase(db):
    job.upsert_outings(
        db, [outing('1', GPX + 'a.gpx', 1), outing('2', GPX + 'b.gpx', 2)], NOW
    )
    transport = Answers({GPX + 'a.gpx': SourceBlocked('HTTP 403')})
    assert run(db, transport) == {'ok': 0, 'failed': 1, 'invalid': 0}
    assert transport.calls == [GPX + 'a.gpx']


def test_tracks_are_deleted_with_their_outing(db):
    job.upsert_outings(db, [outing('1', GPX + 'a.gpx', days_ago=100)], NOW)
    run(db, Answers({}))
    assert set(stored(db)) == {'1'}
    job.purge_partner_outings(db, NOW, 31)
    db.commit()
    assert stored(db) == {}


def test_the_default_config_never_purges_the_outings_nor_their_tracks(
    db, db_connection
):
    """`partners_retention=""` (env.default): old outings and tracks stay."""
    from c2corg_api.tests.partners.test_defaults import read_env

    env = read_env('env.default')
    settings = {
        'partners.retention_days': env['partners_retention'],
        'partners.lookup_retention_days': env['partners_lookup_retention'],
    }
    job.upsert_outings(db, [outing('1', GPX + 'a.gpx', days_ago=400)], NOW)
    run(db, Answers({}))
    db.commit()
    job.purge_partner_outings_job(settings)
    assert set(stored(db)) == {'1'}
    assert db.scalar(select(func.count()).select_from(PartnerOuting)) == 1


def test_the_harvester_runs_the_phase_after_the_outings(db, db_connection):
    """The demo: the gulliver fixtures, then the synthetic tracks of two reports."""
    settings = {
        'harvest.partners.gulliver.enabled': 'true',
        'partners.transport': 'fixtures',
        'partners.fixtures_dir': '',
        'partners.allow_synthetic': 'true',
        'partners.tracks_per_run': '3',
    }
    job.harvest_partner_outings(settings, now=NOW)
    rows = stored(db)
    # newest first: 3 of the 7 outings with a GPX link of the recording
    assert {k: v.status for k, v in rows.items()} == {
        '350553': 'ok',
        '350592': 'ok',
        '350579': 'ok',
    }
    count = db.scalar(
        select(func.count())
        .select_from(PartnerOuting)
        .where(PartnerOuting.gpx_url.is_not(None))
    )
    assert count == 7


# -- the API ----------------------------------------------------------------


@pytest.fixture
def with_track(db, monkeypatch):
    monkeypatch.setattr('c2corg_api.views.partner_outings.today', lambda: TODAY)
    job.upsert_outings(
        db,
        [
            outing('1', MONTECRESTESE, author='user7'),
            outing('2', VALTOURNENCHE, author=None),
            outing('3', None),
        ],
        NOW,
    )
    transport = FixtureTransport(FIXTURES, 'gulliver_tracks', RateLimit(10, 3, 30))
    tracks.harvest_tracks(db, GulliverAdapter, transport, NOW, SETTINGS)
    db.commit()


def test_listing_has_track(client, with_track):
    items = client.get('/partner-outings', status=200).json['items']
    by_id = {i['id']: i for i in items}
    assert by_id['gulliver:1']['has_track'] is True
    assert by_id['gulliver:1']['gpx_url'] == MONTECRESTESE
    assert by_id['gulliver:3']['has_track'] is False
    assert by_id['gulliver:3']['gpx_url'] is None


def test_track_feature(client, with_track):
    response = client.get('/partner-outings/gulliver:1/track', status=200)
    assert response.headers['Cache-Control'] == 'public, max-age=3600'
    feature = response.json
    assert feature['type'] == 'Feature'
    assert feature['id'] == 'gulliver:1'
    assert feature['geometry']['type'] == 'MultiLineString'
    (line,) = feature['geometry']['coordinates']
    assert len(line) == 60
    # EPSG:4326, lon lat, 6 decimals: the points of the file
    assert line[0] == [8.325, 46.155]
    assert feature['properties'] == {
        'source': 'gulliver',
        'url': 'https://www.gulliver.it/itinerari/x/2026/11/26/1/',
        'gpx_url': MONTECRESTESE,
        'author': 'user7',
        'attribution': '© user7 / gulliver.it — CC BY-NC-ND',
        'licence': 'CC BY-NC-ND',
        'point_count': 60,
        'simplified': False,
    }
    # nothing of the file but the points
    for word in ('Synthetic', '2000-01-01', 'hr', 'waypoint', 'ele'):
        assert word not in response.text


def test_track_without_author(client, with_track):
    feature = client.get('/partner-outings/gulliver:2/track', status=200).json
    assert feature['properties']['attribution'] == '© gulliver.it — CC BY-NC-ND'


@pytest.mark.parametrize(
    'item_id',
    ['gulliver:3', 'gulliver:404', 'c2c:1', 'nope:1', 'gulliver', 'gulliver:'],
)
def test_no_track(client, with_track, item_id):
    response = client.get(f'/partner-outings/{item_id}/track', status=404)
    assert response.json['status'] == 'error'
