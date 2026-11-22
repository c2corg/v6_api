import json
import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import requests

from c2corg_api.avalanche_bulletins.cache import CET
from c2corg_api.tests.avalanche_bulletins.test_bra import FIXTURES
from c2corg_api.tests.contract import check_snapshot, contract

BULLETIN = ('GET', '/avalanche-bulletins/regions/{region_id}/latest')
PDF = ('GET', '/avalanche-bulletins/regions/{region_id}/latest/pdf')

GET = 'c2corg_api.avalanche_bulletins.meteofrance.requests.get'
CAAML_GET = 'c2corg_api.avalanche_bulletins.caaml.requests.get'


def answer(status, content=b''):
    """Return a fake answer of the Météo-France API."""
    return Mock(status_code=status, ok=200 <= status < 300, content=content)


def bra(massif):
    with open(os.path.join(FIXTURES, f'BRA_{massif}.xml'), 'rb') as f:
        return f.read()


@pytest.fixture(autouse=True)
def meteofrance_key(monkeypatch):
    """Set the key of the Météo-France API, whose answers the tests fake."""
    monkeypatch.setenv('METEOFRANCE_API_KEY', 'contract-test-key')


@pytest.fixture(autouse=True)
def recorded_day(monkeypatch):
    """Answer as on the day the fixtures were recorded (they get stale after)."""
    monkeypatch.setattr(
        'c2corg_api.avalanche_bulletins.regions._now',
        lambda: datetime(2026, 11, 22, 12, tzinfo=CET),
    )


def caaml(name):
    with open(os.path.join(FIXTURES, name), 'rb') as f:
        return f.read()


def json_answer(status, content=b''):
    """Return a fake answer of a CAAML service."""
    response = answer(status, content)
    response.json.side_effect = lambda: json.loads(content)
    return response


@pytest.mark.usefixtures('client')
class TestAvalancheBulletin:
    @contract(BULLETIN)
    def test_bulletin(self, browser):
        with patch(GET, return_value=answer(200, bra(3))) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
            # the second answer comes from the cache
            browser.get('/avalanche-bulletins/regions/FR-03/latest')
        check_snapshot('avalanche_bulletin', response)
        assert get.call_count == 1
        assert get.call_args.kwargs['params'] == {'id-massif': 3, 'format': 'xml'}
        assert get.call_args.kwargs['headers']['apikey'] == 'contract-test-key'
        [bulletin] = response.json['bulletins']
        assert bulletin['regions'][0]['regionID'] == 'FR-03'

    @contract(BULLETIN)
    def test_no_bulletin_out_of_season(self, browser):
        with patch(GET, return_value=answer(404, b'{"detail":"no matching blob"}')):
            response = browser.get('/avalanche-bulletins/regions/FR-41/latest')
        assert response.json == {'bulletins': []}

    @contract(BULLETIN)
    def test_unknown_region(self, browser):
        with patch(GET) as get:
            response = browser.get(
                '/avalanche-bulletins/regions/FR-71/latest', status=404
            )
            browser.get('/avalanche-bulletins/regions/XX-12/latest', status=404)
            browser.get('/avalanche-bulletins/regions/fr-03/latest', status=422)
        check_snapshot('avalanche_bulletin_unknown_region', response)
        get.assert_not_called()

    @contract(BULLETIN)
    def test_meteofrance_down(self, browser):
        with patch(GET, side_effect=requests.exceptions.ConnectionError('down')):
            response = browser.get(
                '/avalanche-bulletins/regions/FR-03/latest', status=503
            )
        check_snapshot('avalanche_bulletin_unavailable', response)

    @contract(BULLETIN)
    def test_last_bulletin_while_meteofrance_is_down(self, browser):
        with patch(GET, return_value=answer(200, bra(3))):
            browser.get('/avalanche-bulletins/regions/FR-03/latest')
        expired = patch(
            'c2corg_api.avalanche_bulletins.cache.expiration', return_value=0
        )
        with expired, patch(GET, return_value=answer(502)) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()
        assert response.json['bulletins'][0]['regions'][0]['regionID'] == 'FR-03'

    @contract(BULLETIN)
    def test_invalid_bulletin(self, browser):
        with patch(GET, return_value=answer(200, b'<BULLETINS_NEIGE_AVALANCHE')):
            browser.get('/avalanche-bulletins/regions/FR-03/latest', status=503)

    @contract(BULLETIN)
    def test_no_key(self, browser, monkeypatch):
        monkeypatch.delenv('METEOFRANCE_API_KEY')
        with patch(GET) as get:
            browser.get('/avalanche-bulletins/regions/FR-03/latest', status=503)
        get.assert_not_called()


@pytest.mark.usefixtures('client')
class TestAvalancheBulletinPdf:
    @contract(PDF)
    def test_pdf(self, browser):
        with patch(GET, return_value=answer(200, b'%PDF-1.7')) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest/pdf')
        check_snapshot('avalanche_bulletin_pdf', response, ['Content-Disposition'])
        assert response.body == b'%PDF-1.7'
        assert get.call_args.kwargs['params'] == {'id-massif': 3, 'format': 'pdf'}

    @contract(PDF)
    def test_no_pdf_out_of_season(self, browser):
        with patch(GET, return_value=answer(404)):
            browser.get('/avalanche-bulletins/regions/FR-03/latest/pdf', status=404)

    @contract(PDF)
    def test_unknown_region(self, browser):
        browser.get('/avalanche-bulletins/regions/FR-99/latest/pdf', status=404)

    @contract(PDF)
    def test_meteofrance_down(self, browser):
        with patch(GET, return_value=answer(500)):
            browser.get('/avalanche-bulletins/regions/FR-03/latest/pdf', status=503)


@pytest.mark.usefixtures('client')
class TestCaamlBulletin:
    @contract(BULLETIN)
    def test_bulletin_of_a_region(self, browser):
        with patch(
            CAAML_GET, return_value=json_answer(200, caaml('CH_fr.json'))
        ) as get:
            response = browser.get(
                '/avalanche-bulletins/regions/CH-1112/latest', params={'lang': 'fr'}
            )
            # the other region of the same file: from the cache
            other = browser.get(
                '/avalanche-bulletins/regions/CH-1113/latest', params={'lang': 'fr'}
            )
        check_snapshot('avalanche_bulletin_caaml', response)
        get.assert_called_once()
        assert get.call_args.args[0] == 'https://aws.slf.ch/api/bulletin/caaml/fr/json'
        [bulletin] = response.json['bulletins']
        assert [r['regionID'] for r in bulletin['regions']] == ['CH-1112']
        assert bulletin['source']['provider']['name'] == 'SLF'
        assert bulletin['customData']['ALBINA'] == {'mainDate': '2026-11-22'}
        assert [r['regionID'] for r in other.json['bulletins'][0]['regions']] == [
            'CH-1113'
        ]

    @contract(BULLETIN)
    def test_all_the_bulletins_of_a_service(self, browser):
        with patch(CAAML_GET, return_value=json_answer(200, caaml('IT-23_fr.json'))):
            response = browser.get(
                '/avalanche-bulletins/regions/IT-23/latest', params={'lang': 'fr'}
            )
        assert len(response.json['bulletins']) == 3

    @contract(BULLETIN)
    def test_english_when_the_language_is_not_published(self, browser):
        with patch(CAAML_GET, return_value=json_answer(404)) as get:
            response = browser.get(
                '/avalanche-bulletins/regions/SI-1/latest', params={'lang': 'fr'}
            )
        assert get.call_args.args[0].endswith('/SI_en_CAAMLv6.json')
        # no file out of season
        assert response.json == {'bulletins': []}

    @contract(BULLETIN)
    def test_last_season_is_not_shown(self, browser):
        with patch(CAAML_GET, return_value=json_answer(200, caaml('AT-07_en.json'))):
            response = browser.get('/avalanche-bulletins/regions/AT-07-05/latest')
        assert response.json == {'bulletins': []}

    @contract(BULLETIN)
    def test_not_caaml(self, browser):
        with patch(CAAML_GET, return_value=json_answer(200, b'{"bulletins": 3}')):
            browser.get('/avalanche-bulletins/regions/CH-1112/latest', status=503)
        with patch(CAAML_GET, return_value=json_answer(200, b'<html>')):
            browser.get('/avalanche-bulletins/regions/CH-1113/latest', status=503)

    @contract(PDF)
    def test_no_pdf(self, browser):
        with patch(CAAML_GET) as get:
            browser.get('/avalanche-bulletins/regions/CH-1112/latest/pdf', status=404)
        get.assert_not_called()
