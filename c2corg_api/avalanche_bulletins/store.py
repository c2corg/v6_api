"""The harvested avalanche bulletins, in PostgreSQL: written, read, pruned."""
# The bulletins as published (CAAML v6, normalized as on demand), one row by
# publication and language, and the danger of each region on each day.

import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from c2corg_api.avalanche_bulletins.cache import CET, main_date
from c2corg_api.avalanche_bulletins.regions import STALE_AFTER
from c2corg_api.models.avalanche_bulletin import (
    AvalancheBulletin,
    AvalancheBulletinRegion,
)

RATINGS = {'low': 1, 'moderate': 2, 'considerable': 3, 'high': 4, 'very_high': 5}
ASPECTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

# the publications superseded the same day are kept this long
SUPERSEDED_RETENTION = timedelta(days=7)


def save(session, provider, lang, bulletins, source_id=None):
    """Store the bulletins not stored yet: tell if there was any."""
    new = False
    for bulletin in bulletins:
        row = _row(provider, lang, bulletin, source_id)
        id = session.scalar(
            insert(AvalancheBulletin)
            .values(**row)
            .on_conflict_do_nothing(constraint='uq_avalanche_bulletins_publication')
            .returning(AvalancheBulletin.id)
        )
        if id is None:
            continue
        new = True
        for region_id in row['region_ids']:
            _save_region(session, region_id, row, id, summary(bulletin))
    return new


def summary(bulletin):
    """Return the danger of a bulletin: ratings (1-5), problems and aspects."""
    # Up to two elevation bands: a rating with a lower bound is the one above,
    # with an upper bound the one below, without bound both (a band between
    # two bounds is in both). The ratings of the morning and afternoon count
    # alike: the maximum of the day.
    low, high, all_ratings, bound = [], [], [], None
    for rating in bulletin.get('dangerRatings') or []:
        elevation = rating.get('elevation') or {}
        lower, upper = elevation.get('lowerBound'), elevation.get('upperBound')
        bound = bound or lower or upper
        # no_rating, no_snow: no rating
        value = RATINGS.get(rating.get('mainValue'))
        if value is None:
            continue
        all_ratings.append(value)
        if lower or not upper:
            high.append(value)
        if upper or not lower:
            low.append(value)
    problems = []
    aspects = set()
    for problem in bulletin.get('avalancheProblems') or []:
        if problem.get('problemType') and problem['problemType'] not in problems:
            problems.append(problem['problemType'])
        aspects.update(problem.get('aspects') or [])
    # Météo-France: the most dangerous aspects
    meteofrance = (bulletin.get('customData') or {}).get('MeteoFrance') or {}
    aspects.update((meteofrance.get('avalancheProneLocation') or {}).get('aspects', []))
    return {
        'max_rating': max(all_ratings, default=None),
        'rating_low': max(low, default=None),
        'rating_high': max(high, default=None),
        'elevation_bound': bound,
        'problems': problems,
        'aspects': [aspect for aspect in ASPECTS if aspect in aspects],
    }


def latest_for_region(session, region_id, lang, now=None):
    """Return the latest bulletins covering a region, as CAAML (or [])."""
    # as regions.latest_bulletins: those of the latest day, not stale
    now = now or datetime.now(UTC)
    covering = _covering(region_id)
    day = session.scalar(
        select(func.max(AvalancheBulletin.main_date)).where(
            covering, AvalancheBulletin.valid_end > now - STALE_AFTER
        )
    )
    if day is None:
        return []
    return for_region_and_date(session, region_id, day, lang)


def for_region_and_date(session, region_id, day, lang):
    """Return the bulletins covering a region on a day, as CAAML (or [])."""
    rows = session.execute(
        select(
            AvalancheBulletin.provider,
            AvalancheBulletin.lang,
            AvalancheBulletin.region_ids,
            AvalancheBulletin.caaml,
        )
        .where(_covering(region_id), AvalancheBulletin.main_date == day)
        .order_by(AvalancheBulletin.publication_time.desc(), AvalancheBulletin.id)
    ).all()
    return _latest(rows, region_id, lang)


def ratings(session, region_id, date_from, date_to):
    """Return the danger of a region each day of a period (both included)."""
    found = session.scalars(
        select(AvalancheBulletinRegion)
        .where(
            AvalancheBulletinRegion.region_id == region_id,
            AvalancheBulletinRegion.main_date.between(date_from, date_to),
        )
        .order_by(AvalancheBulletinRegion.main_date)
    )
    return [
        {
            'date': row.main_date.isoformat(),
            'maxRating': row.max_rating,
            'ratingLow': row.rating_low,
            'ratingHigh': row.rating_high,
            'elevationBound': row.elevation_bound,
            'problems': row.problems,
            'aspects': row.aspects,
        }
        for row in found
    ]


def prune_superseded(session, now=None):
    """Delete the publications superseded the same day, after a week."""
    # the last publication of each bulletin, language and day is kept
    now = now or datetime.now(UTC)
    newer = aliased(AvalancheBulletin)
    return session.execute(
        delete(AvalancheBulletin).where(
            AvalancheBulletin.publication_time < now - SUPERSEDED_RETENTION,
            exists().where(
                and_(
                    newer.provider == AvalancheBulletin.provider,
                    newer.bulletin_id == AvalancheBulletin.bulletin_id,
                    newer.lang == AvalancheBulletin.lang,
                    newer.main_date == AvalancheBulletin.main_date,
                    newer.publication_time > AvalancheBulletin.publication_time,
                )
            ),
        )
    ).rowcount


def _row(provider, lang, bulletin, source_id):
    valid = bulletin['validTime']
    day = ((bulletin.get('customData') or {}).get('ALBINA') or {}).get(
        'mainDate'
    ) or main_date(valid)
    return {
        'provider': provider,
        'bulletin_id': bulletin.get('bulletinID')
        or f'{bulletin["regions"][0]["regionID"]}_{valid["startTime"]}',
        'lang': bulletin.get('lang') or lang,
        'publication_time': _time(
            bulletin.get('publicationTime') or valid['startTime']
        ),
        'valid_start': _time(valid['startTime']),
        'valid_end': _time(valid['endTime']),
        'main_date': date.fromisoformat(day),
        'region_ids': sorted({r['regionID'] for r in bulletin['regions']}),
        'caaml': bulletin,
        'source_id': source_id,
    }


def _save_region(session, region_id, row, bulletin_id, danger):
    # the latest publication of the day wins; the other languages of the
    # same publication leave it as it is
    insertion = insert(AvalancheBulletinRegion).values(
        region_id=region_id,
        main_date=row['main_date'],
        bulletin=bulletin_id,
        publication_time=row['publication_time'],
        **danger,
    )
    excluded = insertion.excluded
    session.execute(
        insertion.on_conflict_do_update(
            index_elements=['region_id', 'main_date'],
            set_={
                name: excluded[name]
                for name in ('bulletin', 'publication_time', *danger)
            },
            where=AvalancheBulletinRegion.publication_time < excluded.publication_time,
        )
    )


def _covering(region_id):
    # the region or one of its sub-regions (CH: CH-4231), on the rows of a
    # few days (the callers filter on the dates)
    pattern = f'(^|,){re.escape(region_id)}(-[^,]*)?(,|$)'
    return func.array_to_string(AvalancheBulletin.region_ids, ',').regexp_match(pattern)


def _latest(rows, region_id, lang):
    # by provider, the language asked, else English, else the one published;
    # then the latest publication of each region (rows: the latest first)
    by_provider = {}
    for row in rows:
        by_provider.setdefault(row.provider, set()).add(row.lang)
    chosen = {
        provider: lang if lang in langs else 'en' if 'en' in langs else min(langs)
        for provider, langs in by_provider.items()
    }
    found, covered = [], set()
    for row in rows:
        if row.lang != chosen[row.provider]:
            continue
        regions = {
            r for r in row.region_ids if r == region_id or r.startswith(f'{region_id}-')
        }
        if regions - covered:
            found.append(row.caaml)
            covered |= regions
    return found


def _time(value):
    time = datetime.fromisoformat(value)
    return time if time.tzinfo else time.replace(tzinfo=CET)
