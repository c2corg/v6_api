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
# in the cache (s): a new publication changes their key at once, a
# publication changed at the same time (store.save) shows after it
STORED_EXPIRATION = 600


class UnknownRegion(Exception):
    """No service c2c reads publishes bulletins for this region."""


def latest_bulletins(region_id, lang, session=None):
    """Return the latest bulletins covering a region (or its sub-regions)."""
    if session is not None:
        stored = _stored_latest(session, region_id, lang)
        if stored:
            return stored
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


def is_over(day):
    """Tell whether a day is over, in the time zone of the services."""
    return day < _now().date()


def _stored_latest(session, region_id, lang):
    # the database failing, the bulletins are fetched as before
    try:
        day = store.latest_day(session, region_id, _now())
        return day_bulletins(session, region_id, day, lang) if day else []
    except SQLAlchemyError:
        log.exception('Reading the stored bulletins of %s failed', region_id)
        session.rollback()
        return []


def _now():
    return datetime.now(CET)


def _covers(bulletin, region_id):
    return any(
        r['regionID'] == region_id or r['regionID'].startswith(f'{region_id}-')
        for r in bulletin['regions']
    )


def _end(bulletin):
    return end_time(bulletin['validTime'])
