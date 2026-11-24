"""The harvested avalanche bulletins, in PostgreSQL: written, read, pruned."""
# The bulletins as published (CAAML v6, normalized as on demand), one row by
# publication and language, and the danger of each region on each day.

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from c2corg_api.avalanche_bulletins import weather
from c2corg_api.avalanche_bulletins.cache import CET, STALE_AFTER, main_date
from c2corg_api.models.avalanche_bulletin import (
    AvalancheBulletin,
    AvalancheBulletinRegion,
)

RATINGS = {'low': 1, 'moderate': 2, 'considerable': 3, 'high': 4, 'very_high': 5}
ASPECTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

# the publications superseded the same day are kept this long
SUPERSEDED_RETENTION = timedelta(days=7)
# the latest bulletins are of these last days at most
RECENT_DAYS = timedelta(days=3)
# the customData of the bulletins are removed after (months): what
# the history of the danger needs is kept
COMPACT_AFTER_MONTHS = 18


def save(session, provider, lang, bulletins, source_id=None):
    """Store the bulletins new or changed: tell if there was any."""
    new = False
    for bulletin in bulletins:
        bulletin, region_weather = weather.extract(bulletin)
        row = _row(provider, lang, bulletin, source_id)
        insertion = insert(AvalancheBulletin).values(**row)
        # a service may change a publication without changing its time
        changed = {
            name: insertion.excluded[name]
            for name in row
            if name not in ('provider', 'bulletin_id', 'lang', 'publication_time')
        }
        id = session.scalar(
            insertion.on_conflict_do_update(
                constraint='uq_avalanche_bulletins_publication',
                set_=changed,
                where=AvalancheBulletin.caaml != insertion.excluded.caaml,
            ).returning(AvalancheBulletin.id)
        )
        if id is None:
            continue
        new = True
        danger = summary(bulletin)
        for region_id in row['region_ids']:
            _save_region(session, region_id, row, id, danger)
        if region_weather:
            weather.save(
                session,
                provider,
                row['region_ids'],
                row['publication_time'],
                region_weather,
            )
    return new


def region_keys(region_id):
    """Return a region id and the ids of the regions holding it."""
    # AT-07-14-01: AT-07-14, AT-07, AT; the micro-regions of SLF nest by
    # digit too: CH-4231 is in CH-423, CH-42, CH-4
    parts = region_id.split('-')
    keys = ['-'.join(parts[:i]) for i in range(1, len(parts) + 1)]
    if parts[0] == 'CH' and len(parts) == 2:
        keys += [f'CH-{parts[1][:i]}' for i in range(1, len(parts[1]))]
    return sorted(keys)


def summary(bulletin):
    """Return the danger of a bulletin: ratings (1-5), problems and aspects."""
    # All the ratings go to bands, as given. With one elevation bound, a
    # rating with a lower bound is the one above, with an upper bound the
    # one below, without bound both; with more bounds (three bands), only
    # the bands tell. The morning and afternoon count alike: the maximum.
    bands, values, bounds = [], [], set()
    for rating in bulletin.get('dangerRatings') or []:
        elevation = rating.get('elevation') or {}
        # no_rating, no_snow: no rating
        band = {
            'lower': elevation.get('lowerBound'),
            'upper': elevation.get('upperBound'),
            'rating': RATINGS.get(rating.get('mainValue')),
            'period': rating.get('validTimePeriod'),
        }
        bands.append(band)
        bounds.update(b for b in (band['lower'], band['upper']) if b)
        if band['rating'] is not None:
            values.append(band['rating'])
    max_rating = max(values, default=None)
    low = high = bound = None
    if not bounds:
        low = high = max_rating
    elif len(bounds) == 1:
        [bound] = bounds
        rated = [b for b in bands if b['rating'] is not None]
        low = max((b['rating'] for b in rated if not b['lower']), default=None)
        high = max((b['rating'] for b in rated if not b['upper']), default=None)
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
        'max_rating': max_rating,
        'rating_low': low,
        'rating_high': high,
        'elevation_bound': bound,
        'bands': bands,
        'problems': problems,
        'aspects': [aspect for aspect in ASPECTS if aspect in aspects],
    }


def latest_for_region(session, region_id, lang, now=None):
    """Return the latest bulletins covering a region, as CAAML (or [])."""
    day = latest_day(session, region_id, now)
    if day is None:
        return []
    return for_region_and_date(session, region_id, day, lang)


def latest_day(session, region_id, now=None):
    """Return the day of the latest bulletins of a region, None without."""
    # as regions.latest_bulletins: those of the latest day, not stale
    now = now or datetime.now(UTC)
    today = now.astimezone(CET).date()
    return session.scalar(
        select(func.max(AvalancheBulletin.main_date)).where(
            AvalancheBulletin.region_keys.contains([region_id]),
            AvalancheBulletin.main_date >= today - RECENT_DAYS,
            AvalancheBulletin.valid_end > now - STALE_AFTER,
        )
    )


def version(session, region_id, day):
    """Return what changes with a new publication of a region on a day."""
    # the key of the bulletins in the cache: the last publication time and
    # the rows (a row is added by each publication and language)
    last, count, last_id = session.execute(
        select(
            func.max(AvalancheBulletin.publication_time),
            func.count(),
            func.max(AvalancheBulletin.id),
        ).where(
            AvalancheBulletin.region_keys.contains([region_id]),
            AvalancheBulletin.main_date == day,
        )
    ).one()
    return f'{last.isoformat()}:{count}:{last_id}' if count else None


def for_region_and_date(session, region_id, day, lang):
    """Return the bulletins covering a region on a day, as CAAML (or [])."""
    rows = session.execute(
        select(
            AvalancheBulletin.provider,
            AvalancheBulletin.lang,
            AvalancheBulletin.region_ids,
            AvalancheBulletin.caaml,
        )
        .where(
            AvalancheBulletin.region_keys.contains([region_id]),
            AvalancheBulletin.main_date == day,
        )
        .order_by(AvalancheBulletin.publication_time.desc(), AvalancheBulletin.id)
    ).all()
    return _latest(rows, region_id, lang)


def ratings(session, region_id, date_from, date_to):
    """Return the danger of a region and its sub-regions each day of a period.

    By day (both dates included, the days without bulletin left out): the
    highest rating of the regions, for a chart of the region, and the danger
    of each (micro-)region covered.
    """
    found = session.scalars(
        select(AvalancheBulletinRegion)
        .where(
            AvalancheBulletinRegion.region_keys.contains([region_id]),
            AvalancheBulletinRegion.main_date.between(date_from, date_to),
        )
        .order_by(AvalancheBulletinRegion.main_date, AvalancheBulletinRegion.region_id)
    )
    days = {}
    for row in found:
        days.setdefault(row.main_date, []).append(
            {
                'regionId': row.region_id,
                'maxRating': row.max_rating,
                'ratingLow': row.rating_low,
                'ratingHigh': row.rating_high,
                'elevationBound': row.elevation_bound,
                'bands': row.bands,
                'problems': row.problems,
                'aspects': row.aspects,
            }
        )
    return [
        {
            'date': day.isoformat(),
            'maxRating': max(
                (r['maxRating'] for r in regions if r['maxRating']), default=None
            ),
            'regions': regions,
        }
        for day, regions in days.items()
    ]


def prune_superseded(session, now=None):
    """Delete the publications superseded the same day, after a week."""
    # superseded: each of its regions is in a later publication of the
    # provider, in the language, for the day (SLF changes the ids of its
    # bulletins at each publication, and how it groups the regions)
    now = now or datetime.now(UTC)
    return session.execute(
        text(
            """
            DELETE FROM guidebook.avalanche_bulletins b
            WHERE b.publication_time < :before
            AND NOT EXISTS (
                SELECT 1 FROM unnest(b.region_ids) AS r(region_id)
                WHERE NOT EXISTS (
                    SELECT 1 FROM guidebook.avalanche_bulletins n
                    WHERE n.provider = b.provider
                    AND n.lang = b.lang
                    AND n.main_date = b.main_date
                    AND n.publication_time > b.publication_time
                    AND n.region_ids @> ARRAY[r.region_id]
                )
            )
            """
        ),
        {'before': now - SUPERSEDED_RETENTION},
    ).rowcount


def compact(session, now=None, batch=500):
    """Remove the customData of the bulletins older than 18 months."""
    # at all levels, of all the services: the texts, ratings, problems,
    # regions, times and ids are kept; the rows done are marked
    now = now or datetime.now(UTC)
    before = _months_before(now.astimezone(CET).date(), COMPACT_AFTER_MONTHS)
    count = 0
    while True:
        rows = session.execute(
            select(AvalancheBulletin.id, AvalancheBulletin.caaml)
            .where(
                AvalancheBulletin.compacted_at.is_(None),
                AvalancheBulletin.main_date < before,
            )
            .order_by(AvalancheBulletin.id)
            .limit(batch)
        ).all()
        if not rows:
            return count
        for id, caaml in rows:
            session.execute(
                update(AvalancheBulletin)
                .where(AvalancheBulletin.id == id)
                .values(caaml=_without_custom_data(caaml), compacted_at=now)
            )
        count += len(rows)


def _without_custom_data(value):
    if isinstance(value, dict):
        return {
            key: _without_custom_data(item)
            for key, item in value.items()
            if key != 'customData'
        }
    if isinstance(value, list):
        return [_without_custom_data(item) for item in value]
    return value


def _months_before(day, months):
    month = day.year * 12 + day.month - 1 - months
    year, month = divmod(month, 12)
    # the 31st of a shorter month: its last day
    for last in (day.day, 30, 29, 28):
        try:
            return date(year, month + 1, min(day.day, last))
        except ValueError:
            continue


def _row(provider, lang, bulletin, source_id):
    valid = bulletin['validTime']
    region_ids = sorted({r['regionID'] for r in bulletin['regions']})
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
        'region_ids': region_ids,
        'region_keys': sorted({key for r in region_ids for key in region_keys(r)}),
        'caaml': bulletin,
        'source_id': source_id,
        # a compacted publication published again is whole again
        'compacted_at': None,
    }


def _save_region(session, region_id, row, bulletin_id, danger):
    # the latest publication of the day wins (a publication changed at the
    # same time too, then the other languages of it rewrite the same)
    insertion = insert(AvalancheBulletinRegion).values(
        region_id=region_id,
        region_keys=region_keys(region_id),
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
            where=AvalancheBulletinRegion.publication_time <= excluded.publication_time,
        )
    )


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
        regions = {r for r in row.region_ids if region_id in region_keys(r)}
        if regions - covered:
            found.append(row.caaml)
            covered |= regions
    return found


def _time(value):
    time = datetime.fromisoformat(value)
    return time if time.tzinfo else time.replace(tzinfo=CET)
