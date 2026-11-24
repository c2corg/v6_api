from datetime import UTC, date, datetime

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.partner_outing import PartnerOuting, PartnerSource
from c2corg_api.tests.contract import check_snapshot, contract

LISTING = ('GET', '/partner-outings')
SOURCES = ('GET', '/partner-outings/sources')

DAY = date(2026, 11, 22)


@pytest.fixture(autouse=True)
def rows(session, user_ids, monkeypatch):
    """A partner outing and a c2c outing, both in the default window."""
    monkeypatch.setattr(
        'c2corg_api.views.partner_outings.today', lambda: date(2026, 11, 24)
    )
    area = Area(
        area_type='range', locales=[DocumentLocale(lang='fr', title='Belledonne')]
    )
    session.add(area)
    session.flush()
    outing = Outing(
        activities=['skitouring'],
        date_start=DAY,
        date_end=DAY,
        ski_rating='3.2',
        elevation_max=2500,
        locales=[OutingLocale(lang='fr', title='Pointe du Grand Rocher')],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(100 100)'),
    )
    session.add(outing)
    session.flush()
    session.add(
        AreaAssociation(document_id=outing.document_id, area_id=area.document_id)
    )
    session.add(
        Association(
            parent_document_id=user_ids['contributor'],
            parent_document_type='u',
            child_document_id=outing.document_id,
            child_document_type='o',
        )
    )
    session.add(
        PartnerOuting(
            source='skitour',
            external_id='123456',
            url='https://skitour.fr/sorties/123456',
            title="Pic de l'Etendard",
            lang='fr',
            date=DAY,
            author='jdoe',
            region='Grandes Rousses',
            activities=['skitouring'],
            ski_rating_min='3.2',
            ski_rating_max='3.2',
            rating_raw='3.2',
            rating_system='c2c_ski',
            orientations=['N'],
            snow={'top_cm': 40},
            elevation_max=3464,
            geom='SRID=3857;POINT(110 110)',
            geom_quality='summit',
            area_ids=[area.document_id],
        )
    )
    session.add(
        PartnerSource(
            source='skitour',
            status='ok',
            last_success_at=datetime(2026, 11, 24, 10, 15, tzinfo=UTC),
            last_run_at=datetime(2026, 11, 24, 10, 15, tzinfo=UTC),
            last_fetched=10,
            cursor={'secret': 'x'},
        )
    )
    session.flush()


class TestPartnerOutings:
    @contract(LISTING)
    def test_listing(self, browser):
        response = browser.get('/partner-outings')
        check_snapshot('partner_outings_listing', response)
        assert response.json['total'] == 2

    @contract(LISTING)
    def test_listing_filtered(self, browser):
        response = browser.get(
            '/partner-outings',
            params={'sources': 'skitour', 'act': 'skitouring', 'limit': 1},
        )
        check_snapshot('partner_outings_listing_filtered', response)
        assert [i['id'] for i in response.json['items']] == ['skitour:123456']

    @contract(LISTING)
    def test_invalid_parameter(self, browser):
        response = browser.get('/partner-outings', params={'date': 'x'}, status=400)
        check_snapshot('partner_outings_invalid', response)
        assert response.json['errors'][0]['description'] == 'invalid date'

    @contract(LISTING)
    def test_head(self, browser):
        response = browser.request('HEAD', '/partner-outings')
        assert response.status_int == 200


class TestPartnerOutingsSources:
    @contract(SOURCES)
    def test_sources(self, browser):
        response = browser.get('/partner-outings/sources')
        check_snapshot('partner_outings_sources', response)
        assert 'cursor' not in response.text
