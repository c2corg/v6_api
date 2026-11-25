import os
from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

import pytest
import requests
from sqlalchemy import select

from c2corg_api.avalanche_bulletins.cache import UpstreamError
from c2corg_api.avalanche_bulletins.harvesters import (
    CaamlHarvester,
    MeteoFranceHarvester,
)
from c2corg_api.harvest import runner
from c2corg_api.harvest.harvester import NotModified, State
from c2corg_api.models.avalanche_bulletin import (
    AvalancheBulletin,
    AvalancheBulletinRegion,
)
from c2corg_api.models.harvest import HarvestPayload, HarvestSource
from c2corg_api.tests.avalanche_bulletins.test_bra import FIXTURES
from c2corg_api.tests.harvest.conftest import clock, harvest_session  # noqa: F401

MF_GET = 'c2corg_api.avalanche_bulletins.meteofrance.requests.get'
CAAML_GET = 'c2corg_api.avalanche_bulletins.caaml.requests.get'


def fixture(name):
    with open(os.path.join(FIXTURES, name), 'rb') as f:
        return f.read()


def answer(status, content=b'', **headers):
    return Mock(
        status_code=status, ok=200 <= status < 300, content=content, headers=headers
    )


@pytest.fixture(autouse=True)
def meteofrance_key(monkeypatch):
    monkeypatch.setenv('METEOFRANCE_API_KEY', 'harvest-test-key')


def test_sources():
    meteofrance = MeteoFranceHarvester().sources()
    assert len(meteofrance) == 35
    assert {'FR-01', 'FR-03', 'FR-74'} <= set(meteofrance)
    assert 'FR-71' not in meteofrance
    sources = CaamlHarvester().sources()
    assert [s for s in sources if s.startswith('CH:')] == [
        'CH:fr',
        'CH:it',
        'CH:de',
        'CH:en',
    ]
    # the languages of c2c only
    assert 'AT-07:es' in sources
    assert 'AT-07:ca' in sources
    assert not [s for s in sources if s.endswith((':oc', ':zh'))]
    assert {'SI:en', 'SI:de', 'SI:it'} == {s for s in sources if s.startswith('SI:')}


def test_hosts():
    assert MeteoFranceHarvester().host('FR-03') == 'public-api.meteofrance.fr'
    caaml = CaamlHarvester()
    assert caaml.host('CH:fr') == 'aws.slf.ch'
    assert caaml.url('IT-23:fr') == (
        'https://bollettini.aineva.it/albina_files/latest/IT-23_fr_CAAMLv6.json'
    )


def test_conditional_get():
    state = State('"abc"', 'Sun, 22 Nov 2026 16:00:00 GMT')
    ok = answer(200, b'<xml/>', **{'Content-Type': 'application/xml', 'ETag': '"d"'})
    with patch(MF_GET, return_value=ok) as get:
        payload = MeteoFranceHarvester().fetch('FR-03', state)
    headers = get.call_args.kwargs['headers']
    assert headers['If-None-Match'] == '"abc"'
    assert headers['If-Modified-Since'] == 'Sun, 22 Nov 2026 16:00:00 GMT'
    assert headers['apikey'] == 'harvest-test-key'
    assert get.call_args.kwargs['params'] == {'id-massif': 3, 'format': 'xml'}
    assert (payload.content, payload.content_type, payload.etag) == (
        b'<xml/>',
        'application/xml',
        '"d"',
    )
    with patch(CAAML_GET, return_value=answer(304)), pytest.raises(NotModified):
        CaamlHarvester().fetch('CH:fr', state)
    # no file out of season
    with patch(CAAML_GET, return_value=answer(404, b'Not found')):
        assert CaamlHarvester().fetch('CH:fr', State()).content == b''


@pytest.mark.parametrize(
    'failure',
    [answer(500), requests.exceptions.ConnectionError('down')],
)
def test_fetch_errors(failure):
    kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {}
    with patch(CAAML_GET, return_value=failure, **kwargs):
        with pytest.raises(UpstreamError):
            CaamlHarvester().fetch('CH:fr', State())


def test_without_key(monkeypatch):
    monkeypatch.delenv('METEOFRANCE_API_KEY')
    # its sources are disabled
    assert MeteoFranceHarvester().sources() == []
    with pytest.raises(UpstreamError):
        MeteoFranceHarvester().fetch('FR-03', State())


class Few:
    """A harvester limited to a few sources."""

    def __init__(self, harvester, sources):
        harvester.sources = lambda: sources
        self.harvester = harvester


def fake_get(url, params=None, **kwargs):
    # the recorded bulletins: of Mont-Blanc, and of SLF in French
    if params and params['id-massif'] == 3:
        return answer(200, fixture('BRA_3.xml'), **{'Content-Type': 'application/xml'})
    if url == 'https://aws.slf.ch/api/bulletin/caaml/fr/json':
        return answer(200, fixture('CH_fr.json'), ETag='"slf"')
    if 'IT-23_fr' in url:
        return answer(200, b'{"not": "caaml"}')
    return answer(404, b'no matching blob')


def test_harvest(harvest_session, clock):  # noqa: F811
    # in the afternoon window, the day of the recorded bulletins
    clock.now = datetime(2026, 11, 21, 16, 30, tzinfo=UTC)
    harvesters = [
        Few(MeteoFranceHarvester(), ['FR-03', 'FR-41']).harvester,
        Few(CaamlHarvester(), ['CH:fr', 'CH:de', 'IT-23:fr']).harvester,
    ]
    with patch(MF_GET, side_effect=fake_get), patch(CAAML_GET, side_effect=fake_get):
        runner.harvest_tick(all_harvesters=harvesters, workers=1)
    harvest_session.expire_all()
    rows = harvest_session.scalars(
        select(AvalancheBulletin).order_by(AvalancheBulletin.region_ids)
    ).all()
    assert [(r.provider, r.lang, r.region_ids, r.source_id) for r in rows] == [
        ('CH', 'fr', ['CH-1112'], 'avalanche.caaml:CH:fr'),
        ('CH', 'fr', ['CH-1113'], 'avalanche.caaml:CH:fr'),
        ('meteofrance', 'fr', ['FR-03'], 'avalanche.meteofrance:FR-03'),
    ]
    regions = harvest_session.scalars(
        select(AvalancheBulletinRegion.region_id).order_by(
            AvalancheBulletinRegion.region_id
        )
    ).all()
    assert regions == ['CH-1112', 'CH-1113', 'FR-03']
    sources = {s.id: s for s in harvest_session.scalars(select(HarvestSource))}
    # a new publication: hourly until the end of the window
    for id in ('avalanche.meteofrance:FR-03', 'avalanche.caaml:CH:fr'):
        assert sources[id].last_publication == clock.now
        assert sources[id].next_run_at == datetime(2026, 11, 21, 17, 30, tzinfo=UTC)
    assert sources['avalanche.caaml:CH:fr'].etag == '"slf"'
    # no bulletin: 15 minutes later
    for id in ('avalanche.meteofrance:FR-41', 'avalanche.caaml:CH:de'):
        assert sources[id].next_run_at == datetime(2026, 11, 21, 16, 45, tzinfo=UTC)
        assert sources[id].error_count == 0
    invalid = sources['avalanche.caaml:IT-23:fr']
    assert invalid.error_count == 1
    assert 'not CAAML' in invalid.last_error
    # the contents (an empty one for each source without bulletin)
    assert harvest_session.query(HarvestPayload).count() == 4
    assert {r.main_date for r in rows} == {date(2026, 11, 22)}
