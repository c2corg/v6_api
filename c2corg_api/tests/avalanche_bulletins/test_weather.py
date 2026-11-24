import copy
from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from c2corg_api.avalanche_bulletins import caaml, store, weather
from c2corg_api.models.avalanche_bulletin import (
    AvalancheBulletin,
    AvalancheBulletinRegion,
)
from c2corg_api.models.region_weather import RegionWeatherHour, RegionWeatherPeriod
from c2corg_api.tests.avalanche_bulletins.test_store import bra, content

# the publication of the recorded file
PUBLISHED = datetime(2026, 11, 23, 16, tzinfo=UTC)


def slf(lang='fr'):
    bulletins = caaml.parse(content('CH_fr_weather.json'), 'CH', lang)
    for b in bulletins:
        b['lang'] = lang
    return bulletins


def test_extract():
    [bulletin, _] = slf()
    original = copy.deepcopy(bulletin)
    without, found = weather.extract(bulletin)
    assert bulletin == original
    assert len(found) == 3
    assert 'weather' not in without['customData']['CH']
    assert set(without['customData']['CH']) == set(original['customData']['CH']) - {
        'weather'
    }
    assert without['dangerRatings'] == original['dangerRatings']
    [meteofrance] = bra(3)
    assert weather.extract(meteofrance) == (meteofrance, None)


def test_stored_apart(session):
    store.save(session, 'CH', 'fr', slf())
    rows = session.scalars(select(AvalancheBulletin)).all()
    assert len(rows) == 2
    assert all('weather' not in r.caaml['customData']['CH'] for r in rows)
    # 3 days, by hour and by day, for each region
    hours = session.scalars(
        select(RegionWeatherHour).where(RegionWeatherHour.region_id == 'CH-1227')
    ).all()
    assert len(hours) == 72
    assert sum(h.is_forecast for h in hours) == 24
    assert {h.provider for h in hours} == {'CH'}
    assert {h.temperature_elevation_m for h in hours} == {2000}
    periods = session.scalars(
        select(RegionWeatherPeriod)
        .where(RegionWeatherPeriod.region_id == 'CH-1227')
        .order_by(RegionWeatherPeriod.period_start)
    ).all()
    assert [p.is_forecast for p in periods] == [False, False, True]
    assert periods[0].period_end == datetime(2026, 11, 22, 16, tzinfo=UTC)
    assert all(p.new_snow for p in periods)
    assert session.query(RegionWeatherPeriod).count() == 6


def speeds(session):
    session.expire_all()
    return session.scalars(select(RegionWeatherPeriod.wind_speed_kmh)).all()


def test_latest_publication_wins(session):
    store.save(session, 'CH', 'fr', slf())
    first = speeds(session)
    # the other languages: the same
    store.save(session, 'CH', 'de', slf('de'))
    assert speeds(session) == first
    # an earlier one changes nothing
    earlier = slf()
    for b in earlier:
        b['publicationTime'] = '2026-11-23T07:00:00Z'
        b['customData']['CH']['weather'][0]['wind']['speedKmh'] = 98
    store.save(session, 'CH', 'fr', earlier)
    assert 98 not in speeds(session)
    # corrected at the same time, the bulletins unchanged
    corrected = slf()
    for b in corrected:
        b['customData']['CH']['weather'][0]['wind']['speedKmh'] = 99
    assert store.save(session, 'CH', 'fr', corrected) is False
    assert speeds(session).count(99) == 2
    # a later publication
    later = slf()
    for b in later:
        b['publicationTime'] = '2026-11-24T07:00:00Z'
        b['customData']['CH']['weather'][0]['wind']['speedKmh'] = 97
    store.save(session, 'CH', 'fr', later)
    assert speeds(session).count(97) == 2


def test_not_answered_on_demand():
    # as stored: the same answer
    response = Mock(status_code=200, ok=True, content=content('CH_fr_weather.json'))
    with (
        patch(
            'c2corg_api.avalanche_bulletins.caaml.requests.get', return_value=response
        ),
        # without the cache
        patch('c2corg_api.avalanche_bulletins.caaml.cached', lambda key, f: f()),
    ):
        bulletins = caaml.bulletins('CH', 'fr')
    assert len(bulletins) == 2
    assert all('weather' not in b['customData']['CH'] for b in bulletins)


def test_weather_of_days(session):
    store.save(session, 'CH', 'fr', slf())
    found = weather.weather(session, 'CH-1227', date(2026, 11, 24), date(2026, 11, 24))
    # 0:00 to 17:00 (16:00 UTC) included, the last hour given
    assert len(found['hours']) == 18
    assert found['hours'][0]['time'] == '2026-11-23T23:00:00+00:00'
    assert set(found['hours'][0]) == {
        'time',
        'temperatureC',
        'temperatureElevationM',
        'snowfallLimitM',
        'snowfallLimitNullReason',
        'forecast',
    }
    # the period of the 23rd at 17:00 to the 24th at 17:00
    [period] = found['periods']
    assert period['forecast'] is True
    assert set(period['wind']) == {'speedKmh', 'direction', 'highlight'}
    assert weather.weather(
        session, 'CH-12', date(2026, 11, 24), date(2026, 11, 24)
    ) == {
        'hours': [],
        'periods': [],
    }


@pytest.mark.parametrize(
    ('day', 'expected'),
    [
        (date(2028, 5, 22), date(2026, 11, 22)),
        (date(2028, 8, 31), date(2027, 2, 28)),
        (date(2027, 6, 30), date(2025, 12, 30)),
        (date(2027, 1, 15), date(2025, 7, 15)),
    ],
)
def test_months_before(day, expected):
    assert store._months_before(day, 18) == expected


def test_compact(session):
    store.save(session, 'meteofrance', 'fr', bra(3))
    store.save(session, 'CH', 'fr', slf())
    [region] = session.scalars(
        select(AvalancheBulletinRegion).where(
            AvalancheBulletinRegion.region_id == 'FR-03'
        )
    ).all()
    summary = (region.max_rating, region.bands, region.problems, region.aspects)
    # the bulletin of Météo-France is for 2026-11-22: 18 months later, kept
    assert store.compact(session, datetime(2028, 5, 22, 12, tzinfo=UTC)) == 0
    now = datetime(2028, 5, 23, 12, tzinfo=UTC)
    assert store.compact(session, now, batch=1) == 1
    session.expire_all()
    rows = {r.provider: r for r in session.scalars(select(AvalancheBulletin)).all()}
    compacted = rows['meteofrance']
    assert compacted.compacted_at == now
    whole = bra(3)[0]
    # the texts stay, with the ratings, problems, regions, times
    meteofrance = dict(whole['customData']['MeteoFrance'])
    for path in ('weather', 'snowCover', 'newSnow', 'history'):
        assert meteofrance.pop(path)
    assert compacted.caaml['customData'] == {
        'ALBINA': whole['customData']['ALBINA'],
        'MeteoFrance': meteofrance,
    }
    assert set(meteofrance) >= {
        'headline',
        'dangerComment',
        'naturalAvalanches',
        'triggeredAvalanches',
        'avalancheProneLocation',
        'maxDangerRating',
    }
    assert {
        key: value for key, value in compacted.caaml.items() if key != 'customData'
    } == {key: value for key, value in whole.items() if key != 'customData'}
    # the tendency keeps its danger
    assert compacted.caaml['tendency'][0]['customData']['MeteoFrance'] == {
        'maxDangerRating': 'high'
    }
    assert rows['CH'].compacted_at is None
    # once
    assert store.compact(session, now) == 0
    assert store.compact(session, datetime(2028, 5, 25, tzinfo=UTC)) == 2
    session.expire_all()
    slf_compacted = session.scalars(
        select(AvalancheBulletin.caaml).where(AvalancheBulletin.provider == 'CH')
    ).all()
    for caaml_ in slf_compacted:
        assert set(caaml_['customData']['CH']) == set()
        assert caaml_['customData']['ALBINA']['mainDate'] == '2026-11-24'
    assert (region.max_rating, region.bands, region.problems, region.aspects) == (
        summary
    )


def test_compact_job(session):
    from c2corg_api.jobs.harvest import compact_avalanche_bulletins

    store.save(session, 'meteofrance', 'fr', bra(3))
    session.commit()
    # the recorded bulletin is not 18 months old yet
    compact_avalanche_bulletins()
    session.expire_all()
    assert session.scalars(select(AvalancheBulletin.compacted_at)).all() == [None]
