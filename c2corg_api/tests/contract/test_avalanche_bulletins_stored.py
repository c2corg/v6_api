"""The avalanche bulletins read from the database, where they are harvested."""

import copy
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from c2corg_api.avalanche_bulletins import caaml, meteofrance, store
from c2corg_api.avalanche_bulletins.cache import CET
from c2corg_api.models import DBSession
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_avalanche_bulletins import (  # noqa: F401
    BULLETIN,
    CAAML_GET,
    GET,
    answer,
    bra,
    json_answer,
    meteofrance_key,
    recorded_day,
)
from c2corg_api.tests.contract.test_avalanche_bulletins import (
    caaml as fixture,
)

DAY = ('GET', '/avalanche-bulletins/regions/{region_id}/{day}')
RATINGS = ('GET', '/avalanche-bulletins/regions/{region_id}/ratings')


def massif(number=3):
    return meteofrance.parse(bra(number), number)


def slf():
    return caaml.parse(fixture('CH_fr.json'), 'CH', 'fr')


def moved(bulletins, hours=0, main_date=None, rating=None):
    """Return the bulletins published later, maybe for another day."""
    bulletins = copy.deepcopy(bulletins)
    for b in bulletins:
        published = datetime.fromisoformat(b['publicationTime'])
        b['publicationTime'] = (published + timedelta(hours=hours)).isoformat()
        if main_date:
            b['customData']['ALBINA']['mainDate'] = main_date
            b['validTime'] = {
                name: (
                    datetime.fromisoformat(time) + timedelta(hours=hours)
                ).isoformat()
                for name, time in b['validTime'].items()
            }
        if rating:
            b['dangerRatings'] = [{'mainValue': rating}]
    return bulletins


@pytest.mark.usefixtures('client')
class TestLatestStored:
    @contract(BULLETIN)
    def test_from_the_database(self, browser, session):
        store.save(session, 'meteofrance', 'fr', massif())
        session.flush()
        with patch(GET) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_not_called()
        # the same answer as fetched on demand
        check_snapshot('avalanche_bulletin', response)
        assert response.json == {'bulletins': massif()}

    @contract(BULLETIN)
    def test_caaml_from_the_database(self, browser, session):
        store.save(session, 'CH', 'fr', slf())
        session.flush()
        with patch(CAAML_GET) as get:
            response = browser.get(
                '/avalanche-bulletins/regions/CH-1112/latest', params={'lang': 'fr'}
            )
            # a region holding others
            both = browser.get('/avalanche-bulletins/regions/CH/latest')
        get.assert_not_called()
        check_snapshot('avalanche_bulletin_caaml', response)
        [bulletin] = response.json['bulletins']
        assert bulletin['regions'][0]['regionID'] == 'CH-1112'
        assert len(both.json['bulletins']) == 2

    @contract(BULLETIN)
    def test_new_publication_shown_at_once(self, browser, session):
        store.save(session, 'meteofrance', 'fr', massif())
        session.flush()
        browser.get('/avalanche-bulletins/regions/FR-03/latest')
        store.save(session, 'meteofrance', 'fr', moved(massif(), 1, rating='low'))
        session.flush()
        response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        [bulletin] = response.json['bulletins']
        assert bulletin['dangerRatings'] == [{'mainValue': 'low'}]

    @contract(BULLETIN)
    def test_fetched_when_not_stored(self, browser, session):
        # another massif stored only
        store.save(session, 'meteofrance', 'fr', massif(6))
        session.flush()
        with patch(GET, return_value=answer(200, bra(3))) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()
        assert response.json['bulletins'][0]['regions'][0]['regionID'] == 'FR-03'

    @contract(BULLETIN)
    def test_fetched_when_stale(self, browser, session):
        # the last one of the season before
        store.save(
            session, 'meteofrance', 'fr', moved(massif(), -24 * 200, '2026-05-06')
        )
        session.flush()
        with patch(GET, return_value=answer(404)) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()
        assert response.json == {'bulletins': []}

    @contract(BULLETIN)
    def test_fetched_when_no_longer_valid(self, browser, session, monkeypatch):
        store.save(session, 'meteofrance', 'fr', massif())
        session.flush()
        # after the end of its validity (18:00), the next one not harvested yet
        monkeypatch.setattr(
            'c2corg_api.avalanche_bulletins.regions._now',
            lambda: datetime(2026, 11, 22, 18, 30, tzinfo=CET),
        )
        with patch(GET, return_value=answer(200, bra(3))) as get:
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()
        # still within the staleness of the on-demand fetch
        assert len(response.json['bulletins']) == 1

    @contract(BULLETIN)
    def test_no_session_while_fetching(self, browser):
        def fetch(*args, **kwargs):
            # the connection went back to the pool
            assert not DBSession.registry.has()
            return answer(200, bra(3))

        with patch(GET, side_effect=fetch) as get:
            browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()

    @contract(BULLETIN)
    def test_fetched_when_the_database_fails(self, browser):
        failure = OperationalError('SELECT', {}, Exception('down'))
        with (
            patch.object(store, 'latest_day', side_effect=failure),
            patch(GET, return_value=answer(200, bra(3))) as get,
        ):
            response = browser.get('/avalanche-bulletins/regions/FR-03/latest')
        get.assert_called_once()
        assert len(response.json['bulletins']) == 1


@pytest.mark.usefixtures('client')
class TestDay:
    @contract(DAY)
    def test_bulletins_of_a_day(self, browser, session):
        store.save(session, 'CH', 'fr', slf())
        store.save(session, 'CH', 'fr', moved(slf(), -24, '2026-11-21', 'high'))
        session.flush()
        response = browser.get('/avalanche-bulletins/regions/CH-1112/2026-11-22')
        check_snapshot('avalanche_bulletin_day', response)
        [bulletin] = response.json['bulletins']
        assert bulletin['customData']['ALBINA']['mainDate'] == '2026-11-22'
        # the day of the recorded bulletins is not over
        assert response.headers['Cache-Control'] == 'public, max-age=300'
        # the day before is
        before = browser.get(
            '/avalanche-bulletins/regions/CH/2026-11-21', params={'lang': 'de'}
        )
        assert [b['dangerRatings'] for b in before.json['bulletins']] == [
            [{'mainValue': 'high'}],
            [{'mainValue': 'high'}],
        ]
        assert 'immutable' in before.headers['Cache-Control']

    @contract(DAY)
    def test_nothing_stored(self, browser, session):
        store.save(session, 'CH', 'fr', slf())
        session.flush()
        response = browser.get(
            '/avalanche-bulletins/regions/CH-1112/2026-11-20', status=404
        )
        check_snapshot('avalanche_bulletin_unknown_region', response)
        browser.get('/avalanche-bulletins/regions/FR-03/2026-11-22', status=404)

    @contract(DAY)
    @pytest.mark.parametrize('day', ['2026-02-30', '22-11-2026', 'today', '20261122'])
    def test_invalid_day(self, browser, day):
        response = browser.get(
            f'/avalanche-bulletins/regions/CH-1112/{day}', status=400
        )
        assert response.json['errors'] == [
            {
                'location': 'path',
                'name': 'day',
                'description': 'invalid date (YYYY-MM-DD)',
            }
        ]

    @contract(DAY)
    def test_invalid_region(self, browser):
        browser.get('/avalanche-bulletins/regions/ch-1112/2026-11-22', status=422)

    @contract(DAY)
    def test_corrected_day_over(self, browser, session):
        day_before = moved(slf(), -24, '2026-11-21')
        store.save(session, 'CH', 'fr', day_before)
        session.flush()
        url = '/avalanche-bulletins/regions/CH-1112/2026-11-21'
        assert 'immutable' in browser.get(url).headers['Cache-Control']
        # corrected without a new publication time
        corrected = copy.deepcopy(day_before)
        for b in corrected:
            b['dangerRatings'] = [{'mainValue': 'low'}]
        store.save(session, 'CH', 'fr', corrected)
        session.flush()
        [bulletin] = browser.get(url).json['bulletins']
        assert bulletin['dangerRatings'] == [{'mainValue': 'low'}]


@pytest.mark.usefixtures('client')
class TestRatings:
    @contract(RATINGS)
    def test_last_seven_days(self, browser, session):
        store.save(session, 'meteofrance', 'fr', massif())
        store.save(session, 'meteofrance', 'fr', moved(massif(), -24, '2026-11-21'))
        store.save(session, 'meteofrance', 'fr', moved(massif(), -24 * 7, '2026-11-15'))
        session.flush()
        response = browser.get('/avalanche-bulletins/regions/FR-03/ratings')
        check_snapshot('avalanche_bulletin_ratings', response)
        assert [day['date'] for day in response.json['days']] == [
            '2026-11-21',
            '2026-11-22',
        ]
        assert response.json['days'][1]['maxRating'] == 4
        assert response.headers['Cache-Control'] == 'public, max-age=300'

    @contract(RATINGS)
    def test_period(self, browser, session):
        store.save(session, 'CH', 'fr', slf())
        session.flush()
        response = browser.get(
            '/avalanche-bulletins/regions/CH/ratings',
            params={'from': '2026-11-01', 'to': '2026-11-30'},
        )
        [day] = response.json['days']
        assert [r['regionId'] for r in day['regions']] == ['CH-1112', 'CH-1113']
        empty = browser.get(
            '/avalanche-bulletins/regions/CH/ratings', params={'to': '2026-11-10'}
        )
        assert empty.json == {'days': []}

    @contract(RATINGS)
    @pytest.mark.parametrize(
        ('params', 'name'),
        [
            ({'from': '2026-11-31'}, 'from'),
            ({'from': '2026-W47'}, 'from'),
            ({'to': 'today'}, 'to'),
            ({'from': '2026-11-22', 'to': '2026-11-21'}, 'from'),
            ({'from': '2025-11-20', 'to': '2026-11-22'}, 'from'),
        ],
    )
    def test_invalid_period(self, browser, params, name):
        response = browser.get(
            '/avalanche-bulletins/regions/CH/ratings', params=params, status=400
        )
        [error] = response.json['errors']
        assert (error['location'], error['name']) == ('querystring', name)

    @contract(RATINGS)
    def test_cached_and_corrected(self, browser, session):
        store.save(session, 'meteofrance', 'fr', massif())
        session.flush()
        url = '/avalanche-bulletins/regions/FR-03/ratings'
        params = {'from': '2026-11-20', 'to': '2026-11-21'}
        assert browser.get(url, params=params).json == {'days': []}
        # the day before, harvested late (a key of its own: no stale answer)
        store.save(session, 'meteofrance', 'fr', moved(massif(), -24, '2026-11-21'))
        session.flush()
        [day] = browser.get(url, params=params).json['days']
        assert day['maxRating'] == 4
        # corrected at the same time
        corrected = moved(massif(), -24, '2026-11-21', 'low')
        store.save(session, 'meteofrance', 'fr', corrected)
        session.flush()
        [day] = browser.get(url, params=params).json['days']
        assert day['maxRating'] == 1
