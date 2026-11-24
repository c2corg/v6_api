import gzip
import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from c2corg_api.harvest import runner
from c2corg_api.harvest.harvester import Harvester, NotModified, Payload, State
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
        # a new publication
        return payload.content.startswith(b'new')


def sources(session):
    session.expire_all()
    return {s.id: s for s in session.scalars(select(HarvestSource))}


def tick(harvester):
    runner.harvest_tick([harvester], workers=1)


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
    assert a.next_run_at == clock.now + timedelta(minutes=30)
    assert (a.etag, a.last_modified) == ('"v1"', 'Tue, 24 Nov 2026')
    assert a.content_sha256 == hashlib.sha256(b'new data').digest()
    assert a.error_count == 0
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
    assert harvest_session.query(HarvestPayload).count() == 1


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
    assert harvest_session.query(HarvestPayload).count() == 1
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
    tick(harvester)
    assert sorted(sources(harvest_session)) == ['fake:b', 'fake:c']
    # the payloads of a source go with it
    assert harvest_session.query(HarvestPayload).count() == 2


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


@pytest.mark.usefixtures('harvest_session')
def test_threads_and_hosts(monkeypatch, clock):
    # the runs of the tick, in the threads (faked: not on one connection)
    harvester = FakeHarvester({})
    claimed = [('fake', f'fake:{i}', State()) for i in range(6)]
    runs = []
    monkeypatch.setattr(runner, 'sync_sources', lambda session, harvesters: None)
    monkeypatch.setattr(runner, 'claim', lambda session, by_name: claimed)
    monkeypatch.setattr(
        runner, 'run_source', lambda h, id, state: runs.append((h.name, id))
    )
    runner.harvest_tick([harvester])
    assert sorted(runs) == [('fake', f'fake:{i}') for i in range(6)]
    assert runner._host_slot('a.example.org') is runner._host_slot('a.example.org')


def test_prune_payloads(harvest_session, clock):
    harvester = FakeHarvester({'a': Payload(b'old')})
    tick(harvester)
    clock.now += runner.PAYLOAD_RETENTION
    harvester.answers['a'] = Payload(b'recent')
    tick(harvester)
    clock.now += timedelta(minutes=1)
    runner.prune_payloads()
    harvest_session.expire_all()
    [kept] = harvest_session.scalars(select(HarvestPayload)).all()
    assert gzip.decompress(kept.content) == b'recent'


def test_status(harvest_session, clock):
    tick(FakeHarvester({'a': Payload(b'a'), 'b': RuntimeError('down')}))
    assert runner.status(harvest_session) == {
        'fake': {
            'sources': 2,
            'failing': 1,
            'last_success': clock.now.isoformat(),
        }
    }


@pytest.mark.parametrize(
    ('value', 'enabled'),
    [(None, False), ('false', False), ('true', True), (' True ', True), ('1', True)],
)
def test_enabled(value, enabled):
    settings = {} if value is None else {'harvest.enabled': value}
    assert runner.harvest_enabled(settings) is enabled


@pytest.mark.parametrize('on', [False, True])
def test_scheduled_when_on(settings, on):
    scheduler = Mock()
    with patch('c2corg_api.jobs.BackgroundScheduler', return_value=scheduler):
        configure_scheduler_from_config(
            {**settings, 'harvest.enabled': 'true' if on else 'false'}
        )
    ids = [call.kwargs['id'] for call in scheduler.add_job.call_args_list]
    assert ('harvest_tick' in ids) is on
    assert ('prune_harvest' in ids) is on


def test_health(client, harvest_session, clock):
    tick(FakeHarvester({'a': Payload(b'a')}))
    assert client.get('/health').json['harvest'] == {
        'fake': {'sources': 1, 'failing': 0, 'last_success': clock.now.isoformat()}
    }
