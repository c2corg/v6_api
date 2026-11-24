import copy
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from c2corg_api.avalanche_bulletins import caaml, meteofrance, store
from c2corg_api.models.avalanche_bulletin import (
    AvalancheBulletin,
    AvalancheBulletinRegion,
)
from c2corg_api.tests.avalanche_bulletins.test_bra import FIXTURES

# the day of the fixtures of CH and of Météo-France
DAY = date(2026, 11, 22)


def content(name):
    with open(os.path.join(FIXTURES, name), 'rb') as f:
        return f.read()


def bra(massif):
    return meteofrance.parse(content(f'BRA_{massif}.xml'), massif)


def slf(lang='fr'):
    # the file in another language: the same bulletins
    bulletins = caaml.parse(content('CH_fr.json'), 'CH', lang)
    for b in bulletins:
        b['lang'] = lang
    return bulletins


@pytest.mark.parametrize(
    ('ratings', 'expected'),
    [
        # Météo-France: two bands
        (
            [
                {'mainValue': 'considerable', 'elevation': {'upperBound': '2200'}},
                {'mainValue': 'high', 'elevation': {'lowerBound': '2200'}},
            ],
            (4, 3, 4, '2200'),
        ),
        # one rating, the whole day
        ([{'mainValue': 'moderate'}], (2, 2, 2, None)),
        # a band at the treeline, the afternoon higher
        (
            [
                {
                    'mainValue': 'moderate',
                    'elevation': {'lowerBound': 'treeline'},
                    'validTimePeriod': 'earlier',
                },
                {'mainValue': 'low', 'elevation': {'upperBound': 'treeline'}},
                {
                    'mainValue': 'considerable',
                    'elevation': {'lowerBound': 'treeline'},
                    'validTimePeriod': 'later',
                },
            ],
            (3, 1, 3, 'treeline'),
        ),
        # only above: nothing known below
        (
            [{'mainValue': 'high', 'elevation': {'lowerBound': '2000'}}],
            (4, None, 4, '2000'),
        ),
        # no rating, no snow, an unknown value
        (
            [
                {'mainValue': 'no_rating'},
                {'mainValue': 'no_snow', 'elevation': {'lowerBound': '1800'}},
                {'mainValue': 'extreme'},
            ],
            (None, None, None, '1800'),
        ),
        # three bands: only the bands tell
        (
            [
                {'mainValue': 'low', 'elevation': {'upperBound': '1800'}},
                {
                    'mainValue': 'considerable',
                    'elevation': {'lowerBound': '1800', 'upperBound': '2400'},
                },
                {'mainValue': 'moderate', 'elevation': {'lowerBound': '2400'}},
            ],
            (3, None, None, None),
        ),
        # another bound in the afternoon
        (
            [
                {'mainValue': 'low', 'elevation': {'upperBound': '2000'}},
                {
                    'mainValue': 'high',
                    'elevation': {'lowerBound': '2400'},
                    'validTimePeriod': 'later',
                },
            ],
            (4, None, None, None),
        ),
        ([], (None, None, None, None)),
    ],
)
def test_summary_ratings(ratings, expected):
    summary = store.summary({'dangerRatings': ratings})
    assert (
        summary['max_rating'],
        summary['rating_low'],
        summary['rating_high'],
        summary['elevation_bound'],
    ) == expected


def test_summary_problems_and_aspects():
    summary = store.summary(
        {
            'avalancheProblems': [
                {'problemType': 'wind_slab', 'aspects': ['NW', 'N', 'n/a']},
                {'problemType': 'new_snow', 'aspects': ['E']},
                {'problemType': 'wind_slab', 'aspects': ['NE']},
                {'aspects': ['S']},
            ]
        }
    )
    assert summary['problems'] == ['wind_slab', 'new_snow']
    assert summary['aspects'] == ['N', 'NE', 'E', 'S', 'NW']


def test_summary_of_meteofrance():
    [bulletin] = bra(3)
    assert store.summary(bulletin) == {
        'max_rating': 4,
        'rating_low': 3,
        'rating_high': 4,
        'elevation_bound': '2200',
        'bands': [
            {'lower': None, 'upper': '2200', 'rating': 3, 'period': 'all_day'},
            {'lower': '2200', 'upper': None, 'rating': 4, 'period': 'all_day'},
        ],
        'problems': ['new_snow', 'wet_snow'],
        'aspects': ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'],
    }


@pytest.mark.parametrize(
    ('region_id', 'keys'),
    [
        ('FR-03', ['FR', 'FR-03']),
        ('CH-4231', ['CH', 'CH-4', 'CH-42', 'CH-423', 'CH-4231']),
        ('AT-07-14-01', ['AT', 'AT-07', 'AT-07-14', 'AT-07-14-01']),
        ('IT-32-BZ-01', ['IT', 'IT-32', 'IT-32-BZ', 'IT-32-BZ-01']),
        ('SI', ['SI']),
    ],
)
def test_region_keys(region_id, keys):
    assert store.region_keys(region_id) == keys


def test_save_meteofrance(session):
    assert store.save(session, 'meteofrance', 'fr', bra(3)) is True
    # stored once
    assert store.save(session, 'meteofrance', 'fr', bra(3)) is False
    [row] = session.scalars(select(AvalancheBulletin)).all()
    assert row.bulletin_id == 'FR-03_2026-11-21T16:00:00+01:00'
    assert row.lang == 'fr'
    assert row.main_date == DAY
    assert row.region_ids == ['FR-03']
    assert row.region_keys == ['FR', 'FR-03']
    assert row.valid_end == datetime(2026, 11, 22, 17, tzinfo=UTC)
    [region] = session.scalars(select(AvalancheBulletinRegion)).all()
    assert (region.region_id, region.main_date, region.bulletin) == (
        'FR-03',
        DAY,
        row.id,
    )
    assert (region.max_rating, region.rating_low, region.rating_high) == (4, 3, 4)
    assert region.region_keys == ['FR', 'FR-03']
    assert len(region.bands) == 2


def test_publication_changed_at_the_same_time(session):
    store.save(session, 'meteofrance', 'fr', bra(3))
    [changed] = bra(3)
    changed['dangerRatings'] = [{'mainValue': 'moderate'}]
    assert store.save(session, 'meteofrance', 'fr', [changed]) is True
    [row] = session.scalars(select(AvalancheBulletin)).all()
    session.refresh(row)
    assert row.caaml['dangerRatings'] == [{'mainValue': 'moderate'}]
    [region] = session.scalars(select(AvalancheBulletinRegion)).all()
    session.refresh(region)
    assert (region.max_rating, region.elevation_bound) == (2, None)


def test_save_caaml(session):
    assert store.save(session, 'CH', 'fr', slf()) is True
    assert store.save(session, 'CH', 'de', slf('de')) is True
    rows = session.scalars(select(AvalancheBulletin)).all()
    assert sorted((r.lang, r.region_ids[0]) for r in rows) == [
        ('de', 'CH-1112'),
        ('de', 'CH-1113'),
        ('fr', 'CH-1112'),
        ('fr', 'CH-1113'),
    ]
    regions = session.scalars(
        select(AvalancheBulletinRegion).order_by(AvalancheBulletinRegion.region_id)
    ).all()
    assert [(r.region_id, r.main_date, r.max_rating) for r in regions] == [
        ('CH-1112', DAY, 3),
        ('CH-1113', DAY, 3),
    ]


def later(bulletins, hours, rating=None, bulletin_id=None):
    """Return the bulletins published `hours` later, maybe with another danger."""
    bulletins = copy.deepcopy(bulletins)
    for b in bulletins:
        published = datetime.fromisoformat(b['publicationTime'])
        b['publicationTime'] = (published + timedelta(hours=hours)).isoformat()
        if rating:
            b['dangerRatings'] = [{'mainValue': rating}]
        if bulletin_id:
            b['bulletinID'] = f'{bulletin_id}-{b["regions"][0]["regionID"]}'
    return bulletins


def test_region_from_the_latest_publication(session):
    store.save(session, 'meteofrance', 'fr', bra(3))
    assert store.save(session, 'meteofrance', 'fr', later(bra(3), 2, 'low'))
    # an older one, harvested late, changes nothing
    assert store.save(session, 'meteofrance', 'fr', later(bra(3), -2, 'very_high'))
    [region] = session.scalars(select(AvalancheBulletinRegion)).all()
    assert region.max_rating == 1
    assert session.query(AvalancheBulletin).count() == 3


def test_latest_for_region(session):
    store.save(session, 'CH', 'fr', slf())
    store.save(session, 'CH', 'de', slf('de'))
    store.save(session, 'meteofrance', 'fr', bra(3))
    now = datetime(2026, 11, 22, 12, tzinfo=UTC)
    [bulletin] = store.latest_for_region(session, 'CH-1112', 'de', now)
    assert bulletin['regions'][0]['regionID'] == 'CH-1112'
    assert bulletin['customData']['ALBINA']['mainDate'] == '2026-11-22'
    # a region holding others
    found = store.latest_for_region(session, 'CH', 'fr', now)
    assert sorted(b['regions'][0]['regionID'] for b in found) == ['CH-1112', 'CH-1113']
    # Météo-France publishes in French only; the prefix is a whole part
    [bulletin] = store.latest_for_region(session, 'FR-03', 'de', now)
    assert bulletin['lang'] == 'fr'
    assert store.latest_for_region(session, 'FR', 'fr', now)[0]['lang'] == 'fr'
    assert store.latest_for_region(session, 'CH-112', 'fr', now) == []
    assert store.latest_for_region(session, 'FR-0', 'fr', now) == []
    # the micro-regions of SLF nest by digit
    assert len(store.latest_for_region(session, 'CH-111', 'fr', now)) == 2
    # too old
    later = now + timedelta(days=3)
    assert store.latest_for_region(session, 'CH-1112', 'fr', later) == []


def test_latest_publication_only(session):
    # an update of the day, under new bulletin ids (SLF)
    store.save(session, 'CH', 'fr', slf())
    store.save(session, 'CH', 'fr', later(slf(), 1, 'high', 'update'))
    now = datetime(2026, 11, 22, 12, tzinfo=UTC)
    [bulletin] = store.latest_for_region(session, 'CH-1112', 'fr', now)
    assert bulletin['bulletinID'] == 'update-CH-1112'
    found = store.for_region_and_date(session, 'CH-1113', DAY, 'en')
    assert [b['bulletinID'] for b in found] == ['update-CH-1113']
    assert store.for_region_and_date(session, 'CH-1113', date(2026, 11, 21), 'fr') == []


def test_ratings(session):
    store.save(session, 'meteofrance', 'fr', bra(3))
    store.save(session, 'CH', 'fr', slf())
    next_day = later(slf(), 24, 'high', 'next')
    for b in next_day:
        b['customData']['ALBINA']['mainDate'] = '2026-11-23'
    store.save(session, 'CH', 'fr', next_day)
    november = (date(2026, 11, 1), date(2026, 11, 30))
    assert store.ratings(session, 'FR-03', *november) == [
        {
            'date': '2026-11-22',
            'maxRating': 4,
            'regions': [
                {
                    'regionId': 'FR-03',
                    'maxRating': 4,
                    'ratingLow': 3,
                    'ratingHigh': 4,
                    'elevationBound': '2200',
                    'bands': [
                        {
                            'lower': None,
                            'upper': '2200',
                            'rating': 3,
                            'period': 'all_day',
                        },
                        {
                            'lower': '2200',
                            'upper': None,
                            'rating': 4,
                            'period': 'all_day',
                        },
                    ],
                    'problems': ['new_snow', 'wet_snow'],
                    'aspects': ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'],
                }
            ],
        }
    ]
    assert store.ratings(session, 'FR-03', date(2026, 11, 23), date(2026, 11, 30)) == []
    # a region holding others: the highest of the day, and each
    found = store.ratings(session, 'CH', *november)
    assert [(day['date'], day['maxRating']) for day in found] == [
        ('2026-11-22', 3),
        ('2026-11-23', 4),
    ]
    assert [r['regionId'] for r in found[0]['regions']] == ['CH-1112', 'CH-1113']


def test_prune_superseded(session):
    store.save(session, 'meteofrance', 'fr', bra(3))
    store.save(session, 'meteofrance', 'fr', later(bra(3), 1))
    store.save(session, 'meteofrance', 'fr', later(bra(3), 2))
    # another day
    store.save(session, 'meteofrance', 'fr', bra(6))
    published = datetime(2026, 11, 21, 15, 21, tzinfo=UTC)
    # kept a week
    assert store.prune_superseded(session, published + timedelta(days=6)) == 0
    assert store.prune_superseded(session, published + timedelta(days=8)) == 2
    kept = session.scalars(
        select(AvalancheBulletin.publication_time).where(
            AvalancheBulletin.region_ids.contains(['FR-03'])
        )
    ).all()
    assert kept == [published + timedelta(hours=2)]
    assert session.query(AvalancheBulletin).count() == 2
    [region] = session.scalars(
        select(AvalancheBulletinRegion).where(
            AvalancheBulletinRegion.region_id == 'FR-03'
        )
    ).all()
    assert region.bulletin is not None


def test_prune_superseded_under_other_ids(session):
    # SLF: the evening one has a bulletin for both regions, the update of
    # the morning one for each, under new ids
    [both, other] = slf()
    both['regions'] += other['regions']
    store.save(session, 'CH', 'fr', [both])
    [update, _] = later(slf(), 1, 'high', 'update')
    store.save(session, 'CH', 'fr', [update])
    published = datetime(2026, 11, 22, 7, tzinfo=UTC)
    # CH-1113 not published again
    assert store.prune_superseded(session, published + timedelta(days=8)) == 0
    store.save(session, 'CH', 'fr', later(slf(), 2, 'low', 'last'))
    assert store.prune_superseded(session, published + timedelta(days=8)) == 2
    kept = session.scalars(
        select(AvalancheBulletin.bulletin_id).order_by(AvalancheBulletin.bulletin_id)
    ).all()
    assert kept == ['last-CH-1112', 'last-CH-1113']


def test_prune_job(session):
    from c2corg_api.jobs.harvest import prune_harvest

    # published a month ago, then updated
    store.save(session, 'meteofrance', 'fr', later(bra(3), -24 * 30))
    store.save(session, 'meteofrance', 'fr', later(bra(3), -24 * 30 + 1))
    session.commit()
    prune_harvest()
    session.expire_all()
    assert session.query(AvalancheBulletin).count() == 1
