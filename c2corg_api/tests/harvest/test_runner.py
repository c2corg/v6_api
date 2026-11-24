import gzip
import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from c2corg_api.harvest import runner
from c2corg_api.harvest.harvester import (
    Harvester,
    NotModified,
    Payload,
    State,
    Stored,
)
from c2corg_api.harvest.policy import Policy
from c2corg_api.jobs import configure_scheduler_from_config
from c2corg_api.models.harvest import HarvestPayload, HarvestSource

POLICY = Policy(default_every=30, backoff_min=15, backoff_max=120, jitter=0)


class FakeHarvester(Harvester):
    """Answers what the test says: a Payload, or an exception to raise."""

    name = 'fake'
    policy = POLICY

    def __init__(self, answers):
        self.answers = answers
        self.states = {}
        self.stored = []

    def sources(self):
        return list(self.answers)

    def url(self, source):
        return f'https://{source}.example.org/data'

    def fetch(self, source, state):
        self.states[source] = state
        answer = self.answers[source]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def store(self, session, source, payload):
        if payload.content == b'invalid':
            raise ValueError('invalid content')
        self.stored.append((source, payload.content))
        # a new publication; a state to keep
        state = {'seen': len(self.stored)} if payload.content == b'state' else None
        return Stored(payload.content.startswith(b'new'), state)


def sources(session):
    session.expire_all()
    return {s.id: s for s in session.scalars(select(HarvestSource))}


def payloads(session):
    session.expire_all()
    found = session.scalars(select(HarvestPayload).order_by(HarvestPayload.id))
    return [(gzip.decompress(p.content), p.fetched_at) for p in found]


def tick(harvester):
    runner.harvest_tick(all_harvesters=[harvester], workers=1)


def test_first_run(harvest_session, clock):
    harvester = FakeHarvester(
        {'a': Payload(b'new data', 'text/plain', '"v1"', 'Tue, 24 Nov 2026')}
    )
    tick(harvester)
    assert harvester.states['a'] == State()
    assert harvester.stored == [('a', b'new data')]
    a = sources(harvest_session)['fake:a']
    assert a.harvester == 'fake'
    assert a.last_success == a.last_change == a.last_attempt == clock.now
    assert a.last_publication == clock.now
    assert a.next_run_at == clock.now + timedelta(minutes=30)
    assert (a.etag, a.last_modified) == ('"v1"', 'Tue, 24 Nov 2026')
    assert a.content_sha256 == hashlib.sha256(b'new data').digest()
    assert (a.error_count, a.state, a.disabled_at) == (0, None, None)
    [payload] = harvest_session.scalars(select(HarvestPayload)).all()
    assert payload.source_id == 'fake:a'
    assert payload.content_type == 'text/plain'
    assert gzip.decompress(payload.content) == b'new data'


def test_not_due_not_fetched(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'data')})
    tick(harvester)
    harvester.answers['a'] = RuntimeError('fetched too early')
    clock.now += timedelta(minutes=29)
    tick(harvester)
    assert sources(harvest_session)['fake:a'].error_count == 0


def test_same_content_not_stored(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'data', etag='"v1"')})
    tick(harvester)
    first = clock.now
    clock.now += timedelta(minutes=30)
    harvester.answers['a'] = Payload(b'data', etag='"v2"')
    tick(harvester)
    # the state of the conditional GET
    assert harvester.states['a'].etag == '"v1"'
    assert harvester.states['a'].content_sha256 == hashlib.sha256(b'data').digest()
    assert harvester.stored == [('a', b'data')]
    a = sources(harvest_session)['fake:a']
    assert (a.last_change, a.last_success, a.etag) == (first, clock.now, '"v2"')
    assert a.last_publication is None
    assert len(payloads(harvest_session)) == 1


def test_content_seen_again(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'A')})
    for content in (b'A', b'B', b'A'):
        harvester.answers['a'] = Payload(content)
        tick(harvester)
        clock.now += timedelta(minutes=30)
    # kept once, as fetched the last time
    assert payloads(harvest_session) == [
        (b'A', clock.now - timedelta(minutes=30)),
        (b'B', clock.now - timedelta(minutes=60)),
    ]


def test_payloads_not_kept(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'data')})
    harvester.keep_payloads_days = 0
    tick(harvester)
    assert harvester.stored == [('a', b'data')]
    assert payloads(harvest_session) == []


def test_state_kept(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'state')})
    tick(harvester)
    assert sources(harvest_session)['fake:a'].state == {'seen': 1}
    clock.now += timedelta(minutes=30)
    harvester.answers['a'] = Payload(b'other')
    tick(harvester)
    assert harvester.states['a'].data == {'seen': 1}
    # None: left as it is
    assert sources(harvest_session)['fake:a'].state == {'seen': 1}


def test_not_modified(harvest_session, clock):
    harvester = FakeHarvester({'a': NotModified()})
    tick(harvester)
    a = sources(harvest_session)['fake:a']
    assert harvester.stored == []
    assert a.last_success == clock.now
    assert a.last_change is None
    assert a.next_run_at == clock.now + timedelta(minutes=30)


@pytest.mark.parametrize('answer', [RuntimeError('down'), Payload(b'invalid')])
def test_errors_back_off(harvest_session, clock, answer):
    harvester = FakeHarvester({'a': answer, 'b': Payload(b'data')})
    for errors, minutes in [(1, 30), (2, 30), (3, 60), (4, 120), (5, 120)]:
        tick(harvester)
        a = sources(harvest_session)['fake:a']
        assert a.error_count == errors
        assert 'down' in a.last_error or 'invalid' in a.last_error
        assert a.next_run_at == clock.now + timedelta(minutes=minutes)
        assert a.last_success is None
        clock.now = a.next_run_at
    # nothing kept of a failed store, the other source unharmed
    assert len(payloads(harvest_session)) == 1
    assert sources(harvest_session)['fake:b'].error_count == 0
    harvester.answers['a'] = Payload(b'fixed')
    tick(harvester)
    a = sources(harvest_session)['fake:a']
    assert (a.error_count, a.last_error, a.last_success) == (0, None, clock.now)


def test_sources_synced(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'a'), 'b': Payload(b'b')})
    tick(harvester)
    del harvester.answers['a']
    harvester.answers['c'] = Payload(b'c')
    # not at each tick
    clock.now += timedelta(minutes=9)
    tick(harvester)
    assert sorted(sources(harvest_session)) == ['fake:a', 'fake:b']
    clock.now += timedelta(minutes=1)
    tick(harvester)
    found = sources(harvest_session)
    assert found['fake:a'].disabled_at == clock.now
    assert found['fake:c'].disabled_at is None
    # a disabled source is not fetched, nor in the health check
    clock.now += timedelta(hours=1)
    tick(harvester)
    assert found['fake:a'].last_attempt < clock.now - timedelta(hours=1)
    assert runner.status(harvest_session, ['fake'])['fake']['sources'] == 2
    # back
    harvester.answers['a'] = Payload(b'a')
    runner.sync_sources(harvest_session, [harvester])
    a = sources(harvest_session)['fake:a']
    assert (a.disabled_at, a.next_run_at) == (None, clock.now)
    # deleted after a month, with its payloads
    del harvester.answers['a']
    runner.sync_sources(harvest_session, [harvester])
    clock.now += runner.DISABLED_RETENTION + timedelta(minutes=1)
    runner.sync_sources(harvest_session, [harvester])
    assert sorted(sources(harvest_session)) == ['fake:b', 'fake:c']
    assert sorted(content for content, _ in payloads(harvest_session)) == [b'b', b'c']


def test_claim_leases(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'a'), 'b': Payload(b'b')})
    runner.sync_sources(harvest_session, [harvester])
    claimed = runner.claim(harvest_session, {'fake': harvester}, limit=1)
    assert [(name, id) for name, id, _ in claimed] == [('fake', 'fake:a')]
    found = sources(harvest_session)
    # a crashed run is fetched again after the lease
    assert found['fake:a'].next_run_at == clock.now + runner.LEASE
    assert found['fake:b'].next_run_at == clock.now
    # the other harvesters' sources are left to them
    assert runner.claim(harvest_session, {'other': harvester}) == []


def test_claim_within_the_quota(harvest_session, clock):
    harvester = FakeHarvester({s: Payload(b'') for s in 'abc'})
    harvester.requests_per_minute = 2
    runner.sync_sources(harvest_session, [harvester])
    claimed = runner.claim(harvest_session, {'fake': harvester})
    assert [id for _, id, _ in claimed] == ['fake:a', 'fake:b']
    # the next tick
    clock.now += timedelta(minutes=1)
    claimed = runner.claim(harvest_session, {'fake': harvester})
    assert [id for _, id, _ in claimed] == ['fake:c']


def test_lanes_by_host():
    harvester = FakeHarvester({})
    tasks = [(harvester, f'fake:{s}', State()) for s in 'aaaaab']
    lanes = runner._lanes(tasks)
    # two for a host at most, each run in turn
    assert [[id for _, id, _ in lane] for lane in lanes] == [
        ['fake:a', 'fake:a', 'fake:a'],
        ['fake:a', 'fake:a'],
        ['fake:b'],
    ]


@pytest.mark.usefixtures('harvest_session')
def test_threads(monkeypatch, clock):
    # the runs of the tick, in the threads (faked: not on one connection)
    harvester = FakeHarvester({})
    claimed = [('fake', f'fake:{i}', State()) for i in range(6)]
    runs = []
    monkeypatch.setattr(runner, 'sync_sources', lambda session, harvesters: None)
    monkeypatch.setattr(runner, 'claim', lambda session, by_name: claimed)
    monkeypatch.setattr(
        runner, 'run_source', lambda h, id, state: runs.append((h.name, id))
    )
    runner.harvest_tick(all_harvesters=[harvester])
    assert sorted(runs) == [('fake', f'fake:{i}') for i in range(6)]


def test_prune_payloads(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'old')})
    harvester.keep_payloads_days = 10
    tick(harvester)
    clock.now += timedelta(days=10)
    harvester.answers['a'] = Payload(b'recent')
    tick(harvester)
    clock.now += timedelta(minutes=1)
    runner.prune_payloads([harvester])
    assert [content for content, _ in payloads(harvest_session)] == [b'recent']


def test_status(harvest_session, clock):
    tick(FakeHarvester({'a': Payload(b'a'), 'b': RuntimeError('down')}))
    assert runner.status(harvest_session, ['fake']) == {
        'fake': {
            'sources': 2,
            'failing': 1,
            'last_success': clock.now.isoformat(),
        }
    }
    # a harvester of another version of the code
    assert runner.status(harvest_session) == {}


@pytest.mark.parametrize(
    ('settings', 'enabled'),
    [
        ({}, False),
        ({'harvest.enabled': 'false'}, False),
        ({'harvest.enabled': ' True '}, True),
        ({'harvest.enabled': '1'}, True),
        ({'harvest.enabled': 'true', 'harvest.fake.enabled': 'false'}, False),
        ({'harvest.enabled': 'false', 'harvest.fake.enabled': 'true'}, True),
        # empty in the .ini: as harvest.enabled
        ({'harvest.enabled': 'true', 'harvest.fake.enabled': ''}, True),
        ({'harvest.enabled': 'false', 'harvest.fake.enabled': ' '}, False),
    ],
)
def test_enabled(settings, enabled):
    assert runner.harvest_enabled(settings, 'fake') is enabled


@pytest.mark.parametrize(
    ('switches', 'on'),
    [
        ({'harvest.enabled': 'false'}, False),
        ({'harvest.enabled': 'true'}, True),
        (
            {'harvest.enabled': 'false', 'harvest.avalanche.caaml.enabled': 'true'},
            True,
        ),
    ],
)
def test_scheduled_when_on(settings, switches, on):
    scheduler = Mock()
    with patch('c2corg_api.jobs.BackgroundScheduler', return_value=scheduler):
        configure_scheduler_from_config({**settings, **switches})
    ids = [call.kwargs['id'] for call in scheduler.add_job.call_args_list]
    assert ('harvest_tick' in ids) is on
    assert ('prune_harvest' in ids) is on
    assert ('compact_avalanche_bulletins' in ids) is on


def test_enabled_harvesters():
    names = [
        h.name
        for h in runner.enabled_harvesters(
            {'harvest.enabled': 'true', 'harvest.avalanche.meteofrance.enabled': 'no'}
        )
    ]
    assert names == ['avalanche.caaml']


def test_health(client, harvest_session, clock, monkeypatch):
    harvester = FakeHarvester({'a': Payload(b'a')})
    monkeypatch.setattr(runner, 'harvesters', lambda: [harvester])
    tick(harvester)
    assert client.get('/health').json['harvest'] == {
        'fake': {'sources': 1, 'failing': 0, 'last_success': clock.now.isoformat()}
    }
