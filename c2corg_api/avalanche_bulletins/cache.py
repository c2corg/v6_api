"""The cache of the avalanche bulletins, in Redis, following the publications."""
# Fetched on demand: a bulletin is kept a short time around the publications,
# longer otherwise. The last copy is answered while its service does not answer.

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dogpile.cache.api import NO_VALUE

from c2corg_api import caching
from c2corg_api.caching import cache_avalanche_bulletin

log = logging.getLogger(__name__)

# the time zone of the services of the Alps and the Pyrenees
CET = ZoneInfo('Europe/Paris')

# the services publish at about 16:00-17:00 (Météo-France, SLF, Euregio...),
# and some update their bulletin at about 08:00
PUBLICATIONS = [(time(7, 30), time(10, 0)), (time(15, 30), time(18, 30))]
EXPIRATION_AT_PUBLICATION = 600
EXPIRATION = 3600

# below the 15 s of the lock of the cache (caching.configure_caches): a
# longer fetch would lose the lock, and the cache be taken as down
TIMEOUT = (3, 10)

USER_AGENT = 'camptocamp.org avalanche bulletins (+https://www.camptocamp.org)'


class UpstreamError(Exception):
    """The service did not answer, answered an invalid bulletin, or has no key."""


def expiration(now=None):
    """Return how long a bulletin is kept (s): less around the publications."""
    now = (now or datetime.now(CET)).astimezone(CET).time()
    if any(start <= now <= end for start, end in PUBLICATIONS):
        return EXPIRATION_AT_PUBLICATION
    return EXPIRATION


def cached(key, fetch):
    """Return the value of `fetch`, from the cache, else the last copy if it fails."""
    key = f'{caching.CACHE_VERSION}:{key}'
    try:
        return caching.get_or_create(
            cache_avalanche_bulletin, key, fetch, expiration_time=expiration()
        )
    except UpstreamError:
        stale = caching.get(cache_avalanche_bulletin, key)
        if stale is NO_VALUE:
            raise
        log.warning('The service did not answer, answering the last copy of %s', key)
        return stale


def end_time(valid_time):
    """Return the end of the validity of a bulletin (CET when without offset)."""
    end = datetime.fromisoformat(valid_time['endTime'])
    return end if end.tzinfo else end.replace(tzinfo=CET)


def main_date(valid_time):
    """Return the day a bulletin is valid for, from its validity (YYYY-MM-DD)."""
    # the last instant of the validity, in local time: a bulletin valid until
    # 17:00, or until midnight, is the one of that day
    end = end_time(valid_time)
    return (end.astimezone(CET) - timedelta(seconds=1)).date().isoformat()
