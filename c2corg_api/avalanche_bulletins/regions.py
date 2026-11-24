"""The avalanche bulletins of an EAWS region, whatever its service."""
# Read from the database, where the scheduler stores them (harvesters), else
# fetched on demand: a region not harvested (yet) answers as before.

import logging
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from c2corg_api import caching
from c2corg_api.avalanche_bulletins import caaml, meteofrance, store
from c2corg_api.avalanche_bulletins.cache import CET, STALE_AFTER, end_time
from c2corg_api.caching import cache_avalanche_bulletin

log = logging.getLogger(__name__)

# the bulletins of a day not over, read from the database, are kept this long
# in the cache (s); a new or changed bulletin changes their key at once
# (store.version), the key of a day over too
STORED_EXPIRATION = 600


class UnknownRegion(Exception):
    """No service c2c reads publishes bulletins for this region."""


def latest_bulletins(region_id, lang):
    """Return the latest bulletins covering a region, fetched on demand."""
    massif = meteofrance.massif_of(region_id)
    if massif is not None:
        found = meteofrance.bulletin(massif)['bulletins']
    else:
        service_id = caaml.service_of(region_id)
        if service_id is None:
            raise UnknownRegion(region_id)
        found = [b for b in caaml.bulletins(service_id, lang) if _covers(b, region_id)]
    oldest = _now() - STALE_AFTER
    return [b for b in found if _end(b) > oldest]


def day_bulletins(session, region_id, day, lang):
    """Return the bulletins of a region for a day (their main date), stored."""
    version = store.version(session, region_id, day)
    if version is None:
        return []
    key = f'{caching.CACHE_VERSION}:stored:{region_id}:{day}:{lang}:{version}'
    return caching.get_or_create(
        cache_avalanche_bulletin,
        key,
        lambda: store.for_region_and_date(session, region_id, day, lang),
        # a day over does not change anymore
        expiration_time=-1 if is_over(day) else STORED_EXPIRATION,
    )


def stored_latest(session, region_id, lang):
    """Return the stored bulletins of a region still valid, [] without."""
    # the database failing, the bulletins are fetched as before
    try:
        day = store.latest_day(session, region_id, _now(), current=True)
        return day_bulletins(session, region_id, day, lang) if day else []
    except SQLAlchemyError:
        log.exception('Reading the stored bulletins of %s failed', region_id)
        session.rollback()
        return []


def ratings(session, region_id, date_from, date_to):
    """Return the danger of a region over days (store.ratings), cached."""
    version = store.ratings_version(session, region_id, date_from, date_to)
    key = f'{caching.CACHE_VERSION}:ratings:{region_id}:{date_from}:{date_to}:{version}'
    return caching.get_or_create(
        cache_avalanche_bulletin,
        key,
        lambda: store.ratings(session, region_id, date_from, date_to),
        expiration_time=-1 if is_over(date_to) else STORED_EXPIRATION,
    )


def is_over(day):
    """Tell whether a day is over, in the time zone of the services."""
    return day < _now().date()


def _now():
    return datetime.now(CET)


def _covers(bulletin, region_id):
    # as the database (CH-4 holds CH-4231)
    return any(
        region_id in store.region_keys(r['regionID']) for r in bulletin['regions']
    )


def _end(bulletin):
    return end_time(bulletin['validTime'])
