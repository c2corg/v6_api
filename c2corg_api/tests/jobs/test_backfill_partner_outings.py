"""TEMPORARY: the backfill job of the partner outings, on fixtures (no network).

Delete with the other `backfill_*` files (c2corg/v6_api#2763).
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from c2corg_api.jobs import backfill_partner_outings as backfill
from c2corg_api.jobs import harvest_partner_outings as harvest
from c2corg_api.models.backfill_partner_state import BackfillPartnerState
from c2corg_api.models.harvest import HarvestSource
from c2corg_api.models.partner_outing import (
    PartnerLookup,
    PartnerOuting,
    PartnerSource,
)
from c2corg_api.partners.adapter import SourceDown
from c2corg_api.partners.model import HarvestedOuting
from c2corg_api.scripts.jobs import backfill_partners as cli

UTC = datetime.UTC
# the day of the recording of the backfill fixtures: no date shift
NOW = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
FLOOR = datetime.date(2026, 10, 1)
SETTINGS = {
    'harvest.partners.enabled': 'true',
    'partners.transport': 'fixtures',
    'partners.allow_synthetic': 'true',
}


@pytest.fixture
def db(db_connection):
    with Session(db_connection, join_transaction_mode='create_savepoint') as session:
        yield session


def outings(db, source):
    return db.scalars(select(PartnerOuting).where(PartnerOuting.source == source)).all()


def state(db, source):
    db.expire_all()
    return db.get(BackfillPartnerState, source)


def test_a_step_stores_the_outings_and_its_cursor(db):
    summary = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=1
    )
    assert summary['status'] == 'ok'
    assert summary['requests'] == 1
    assert summary['cursor'] == {'state': 0, 'page': 2}
    rows = outings(db, 'skitourenportal')
    assert len(rows) == summary['upserted'] == summary['fetched'] == 3
    assert all(row.date >= FLOOR for row in rows)
    row = state(db, 'skitourenportal')
    assert row.cursor == {'state': 0, 'page': 2}
    assert row.floor == FLOOR
    assert (row.steps, row.requests, row.upserted) == (1, 1, 3)
    assert row.last_status == 'ok' and row.finished_at is None


def test_the_steps_resume_until_done(db):
    first = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=1
    )
    second = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=20
    )
    assert second['status'] == 'ok'
    assert second['cursor'] == {'state': 5, 'page': 1, 'done': True}
    # the first page is not read again
    assert second['requests'] == 7
    row = state(db, 'skitourenportal')
    assert row.finished_at == NOW
    assert row.steps == 2 and row.requests == 8
    assert row.upserted == first['upserted'] + second['upserted']
    done = backfill.backfill_source(db, 'skitourenportal', SETTINGS, NOW, FLOOR)
    assert done['status'] == 'done' and done['requests'] == 0
    assert state(db, 'skitourenportal').steps == 2


def test_the_harvest_state_is_left_alone(db):
    before = (
        db.scalar(select(func.count()).select_from(PartnerSource)),
        db.scalar(select(func.count()).select_from(HarvestSource)),
    )
    backfill.backfill_source(
        db, 'gipfelbuch', SETTINGS, NOW, datetime.date(2026, 11, 22)
    )
    after = (
        db.scalar(select(func.count()).select_from(PartnerSource)),
        db.scalar(select(func.count()).select_from(HarvestSource)),
    )
    assert before == after
    assert db.get(PartnerSource, 'gipfelbuch') is None


def test_the_lookups_are_shared_with_the_harvest(db):
    backfill.backfill_source(
        db, 'gipfelbuch', SETTINGS, NOW, datetime.date(2026, 11, 22), details=2
    )
    keys = db.scalars(
        select(PartnerLookup.key).where(PartnerLookup.source == 'gipfelbuch')
    ).all()
    assert len([k for k in keys if k.startswith('summit:')]) == 2


def test_an_outing_of_the_harvest_is_updated_not_duplicated(db):
    summary = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=1
    )
    row = outings(db, 'skitourenportal')[0]
    first_seen, row_id = row.first_seen_at, row.id
    harvested = HarvestedOuting(
        source='skitourenportal',
        external_id=row.external_id,
        url=row.url,
        title='An older title',
        date=row.date,
        activities=('skitouring',),
    )
    harvest.upsert_outings(db, [harvested], NOW - datetime.timedelta(days=1))
    db.commit()
    backfill.reset_sources(db, ['skitourenportal'])
    again = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=1
    )
    assert again['upserted'] == summary['upserted']
    db.expire_all()
    rows = outings(db, 'skitourenportal')
    assert len(rows) == summary['upserted']
    same = db.get(PartnerOuting, row_id)
    assert same.title == row.title != 'An older title'
    assert same.first_seen_at == first_seen


def test_a_failed_step_keeps_the_cursor_and_stores_nothing(db):
    backfill.backfill_source(db, 'skitourenportal', SETTINGS, NOW, FLOOR, pages=1)
    count = len(outings(db, 'skitourenportal'))

    class Down:
        request_count = 1

        def get(self, url, *, params=None, headers=None):
            raise SourceDown(f'HTTP 503 from {url}')

    summary = backfill.backfill_source(
        db, 'skitourenportal', SETTINGS, NOW, FLOOR, transport=Down()
    )
    assert summary['status'] == 'down'
    assert summary['upserted'] == 0
    row = state(db, 'skitourenportal')
    assert row.cursor == {'state': 0, 'page': 2}
    assert row.last_status == 'down' and 'HTTP 503' in row.last_detail
    assert row.steps == 2
    assert len(outings(db, 'skitourenportal')) == count


def test_a_first_step_that_fails_records_it(db):
    class Down:
        request_count = 1

        def get(self, url, *, params=None, headers=None):
            raise SourceDown('timeout')

    summary = backfill.backfill_source(
        db, 'onice', SETTINGS, NOW, FLOOR, transport=Down()
    )
    assert summary['status'] == 'down'
    row = state(db, 'onice')
    assert row.cursor is None and row.last_status == 'down'


def test_synthetic_fixtures_need_the_switch(db):
    settings = {**SETTINGS, 'partners.allow_synthetic': 'false'}
    summary = backfill.backfill_source(db, 'skitour', settings, NOW, FLOOR)
    assert summary['status'] == 'disabled'
    assert outings(db, 'skitour') == []


def test_skitour_on_the_fixtures(db):
    summary = backfill.backfill_source(
        db, 'skitour', SETTINGS, NOW, datetime.date(2025, 1, 1)
    )
    # recorded on 2026-11-25: dates shifted by 3 days, as the harvest does
    assert summary['status'] == 'ok'
    assert summary['cursor']['done'] is True
    old = db.scalar(
        select(PartnerOuting).where(
            PartnerOuting.source == 'skitour', PartnerOuting.external_id == '188918'
        )
    )
    assert old.date == datetime.date(2025, 12, 16)


def test_a_source_held_by_another_step_is_skipped(db):
    with patch.object(backfill, '_locked_state', return_value=None):
        summary = backfill.backfill_source(db, 'onice', SETTINGS, NOW, FLOOR)
    assert summary['status'] == 'busy'


def test_the_secrets_are_masked(db, monkeypatch):
    monkeypatch.setenv('SKITOUR_API_KEY', 'sekret-key')

    class Leaky:
        request_count = 1

        def get(self, url, *, params=None, headers=None):
            raise SourceDown(f'timeout on {url}?cle={headers["cle"]}')

    settings = {**SETTINGS, 'partners.transport': 'http'}
    summary = backfill.backfill_source(
        db, 'skitour', settings, NOW, FLOOR, transport=Leaky()
    )
    assert summary['status'] == 'down'
    assert 'sekret-key' not in summary['detail']
    assert 'sekret-key' not in state(db, 'skitour').last_detail


def test_backfill_partner_outings_runs_steps(db_connection):
    summaries = backfill.backfill_partner_outings(
        SETTINGS,
        ['skitourenportal', 'onice'],
        floor=FLOOR,
        steps=3,
        pages=4,
        details=0,
        now=NOW,
    )
    by_source = {}
    for summary in summaries:
        by_source.setdefault(summary['source'], []).append(summary['status'])
    # skitourenportal: 8 pages, done in the second step; onice: 5 pages
    assert by_source == {'skitourenportal': ['ok', 'ok'], 'onice': ['ok', 'ok']}


def test_the_sources_to_backfill(monkeypatch):
    monkeypatch.delenv('PARTNERS_BACKFILL_SOURCES', raising=False)
    on = {'harvest.partners.enabled': 'true'}
    assert backfill.backfill_sources(on) == []
    assert backfill.backfill_sources(on, ['all']) == list(backfill.BACKFILLERS)
    off = {**on, 'harvest.partners.onice.enabled': 'false'}
    assert backfill.backfill_sources(off, ['onice', 'bivouak']) == ['bivouak']
    assert backfill.backfill_sources(off, ['onice'], force=True) == ['onice']
    monkeypatch.setenv('PARTNERS_BACKFILL_SOURCES', 'gipfelbuch,skitour')
    assert backfill.backfill_sources(on) == ['skitour', 'gipfelbuch']
    with pytest.raises(ValueError, match='nowhere'):
        backfill.backfill_sources(on, ['nowhere'])


def test_the_default_floor(monkeypatch):
    monkeypatch.delenv('PARTNERS_BACKFILL_FLOOR', raising=False)
    today = datetime.date(2026, 11, 28)
    assert backfill.configured_floor({}, today) == datetime.date(2022, 9, 1)
    monkeypatch.setenv('PARTNERS_BACKFILL_FLOOR', '2020-01-01')
    assert backfill.configured_floor({}, today) == datetime.date(2020, 1, 1)


def test_the_scheduler_job_only_when_configured(monkeypatch):
    monkeypatch.delenv('PARTNERS_BACKFILL_SOURCES', raising=False)
    scheduler = MagicMock()
    backfill.register_backfill_job(scheduler, {'harvest.partners.enabled': 'true'})
    scheduler.add_job.assert_not_called()
    monkeypatch.setenv('PARTNERS_BACKFILL_SOURCES', 'all')
    monkeypatch.setenv('PARTNERS_BACKFILL_EVERY_MINUTES', '30')
    backfill.register_backfill_job(scheduler, {'harvest.partners.enabled': 'true'})
    kwargs = scheduler.add_job.call_args.kwargs
    assert kwargs['id'] == 'backfill_partner_outings'
    assert kwargs['minutes'] == 30 and kwargs['max_instances'] == 1


def test_the_scheduler_registers_it(monkeypatch):
    from c2corg_api import jobs

    monkeypatch.setenv('PARTNERS_BACKFILL_SOURCES', 'onice')
    added = []
    scheduler = MagicMock()
    scheduler.add_job.side_effect = lambda *a, **k: added.append(k.get('id'))
    with (
        patch.object(jobs, 'BackgroundScheduler', return_value=scheduler),
        patch.object(jobs.atexit, 'register'),
    ):
        jobs.configure_scheduler_from_config({'harvest.partners.enabled': 'true'})
    assert 'backfill_partner_outings' in added


def test_the_command_line(db_connection, capsys, monkeypatch):
    monkeypatch.setattr(cli, 'setup_logging', lambda uri: None)
    monkeypatch.setattr(cli, 'get_appsettings', lambda uri, options: SETTINGS)
    monkeypatch.setattr(cli, 'engine_from_config', lambda *a: None)
    monkeypatch.setattr(cli.DBSession, 'configure', lambda **kw: None)
    code = cli.main(
        ['x', 'test.ini', '--sources', 'skitourenportal', '--floor', '2026-10-01']
    )
    assert code == 0
    assert 'skitourenportal: ok' in capsys.readouterr().out
    assert cli.main(['x', 'test.ini', '--status']) == 0
    assert 'skitourenportal: ok' in capsys.readouterr().out
    assert cli.main(['x', 'test.ini', '--sources', 'nowhere']) == 2
