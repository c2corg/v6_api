import os
from unittest.mock import Mock, patch

import pytest
import requests

from c2corg_api.tests.avalanche_bulletins.test_bra import FIXTURES
from c2corg_api.tests.contract import check_snapshot, contract

BULLETIN = ('GET', '/avalanche-bulletins/regions/{region_id}')
PDF = ('GET', '/avalanche-bulletins/regions/{region_id}/pdf')

GET = 'c2corg_api.avalanche_bulletins.meteofrance.requests.get'


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


@pytest.mark.usefixtures('client')
class TestAvalancheBulletin:
    @contract(BULLETIN)
    def test_bulletin(self, browser):
        with patch(GET, return_value=answer(200, bra(3))) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03')
            # the second answer comes from the cache
            browser.get('/avalanche-bulletins/regions/FR-03')
        check_snapshot('avalanche_bulletin', response)
        assert get.call_count == 1
        assert get.call_args.kwargs['params'] == {'id-massif': 3, 'format': 'xml'}
        assert get.call_args.kwargs['headers'] == {'apikey': 'contract-test-key'}
        [bulletin] = response.json['bulletins']
        assert bulletin['regions'][0]['regionID'] == 'FR-03'

    @contract(BULLETIN)
    def test_no_bulletin_out_of_season(self, browser):
        with patch(GET, return_value=answer(404, b'{"detail":"no matching blob"}')):
            response = browser.get('/avalanche-bulletins/regions/FR-41')
        assert response.json == {'bulletins': []}

    @contract(BULLETIN)
    def test_unknown_region(self, browser):
        with patch(GET) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-71', status=404)
            browser.get('/avalanche-bulletins/regions/CH-4231', status=422)
        check_snapshot('avalanche_bulletin_unknown_region', response)
        get.assert_not_called()

    @contract(BULLETIN)
    def test_meteofrance_down(self, browser):
        with patch(GET, side_effect=requests.exceptions.ConnectionError('down')):
            response = browser.get('/avalanche-bulletins/regions/FR-03', status=503)
        check_snapshot('avalanche_bulletin_unavailable', response)

    @contract(BULLETIN)
    def test_last_bulletin_while_meteofrance_is_down(self, browser):
        with patch(GET, return_value=answer(200, bra(3))):
            browser.get('/avalanche-bulletins/regions/FR-03')
        expired = patch(
            'c2corg_api.avalanche_bulletins.meteofrance.expiration', return_value=0
        )
        with expired, patch(GET, return_value=answer(502)) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03')
        get.assert_called_once()
        assert response.json['bulletins'][0]['regions'][0]['regionID'] == 'FR-03'

    @contract(BULLETIN)
    def test_invalid_bulletin(self, browser):
        with patch(GET, return_value=answer(200, b'<BULLETINS_NEIGE_AVALANCHE')):
            browser.get('/avalanche-bulletins/regions/FR-03', status=503)

    @contract(BULLETIN)
    def test_no_key(self, browser, monkeypatch):
        monkeypatch.delenv('METEOFRANCE_API_KEY')
        with patch(GET) as get:
            browser.get('/avalanche-bulletins/regions/FR-03', status=503)
        get.assert_not_called()


@pytest.mark.usefixtures('client')
class TestAvalancheBulletinPdf:
    @contract(PDF)
    def test_pdf(self, browser):
        with patch(GET, return_value=answer(200, b'%PDF-1.7')) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/pdf')
        check_snapshot('avalanche_bulletin_pdf', response, ['Content-Disposition'])
        assert response.body == b'%PDF-1.7'
        assert get.call_args.kwargs['params'] == {'id-massif': 3, 'format': 'pdf'}

    @contract(PDF)
    def test_no_pdf_out_of_season(self, browser):
        with patch(GET, return_value=answer(404)):
            browser.get('/avalanche-bulletins/regions/FR-03/pdf', status=404)

    @contract(PDF)
    def test_unknown_region(self, browser):
        browser.get('/avalanche-bulletins/regions/FR-99/pdf', status=404)

    @contract(PDF)
    def test_meteofrance_down(self, browser):
        with patch(GET, return_value=answer(500)):
            browser.get('/avalanche-bulletins/regions/FR-03/pdf', status=503)
