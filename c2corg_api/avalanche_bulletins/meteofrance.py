"""The avalanche bulletins of Météo-France (DPBRA API), cached in Redis."""
# Fetched on demand, with the key of the association (METEOFRANCE_API_KEY).
# The last copy is answered while Météo-France does not answer.

import logging
import os
from datetime import datetime, time

import requests
from dogpile.cache.api import NO_VALUE

from c2corg_api import caching
from c2corg_api.avalanche_bulletins.bra import PARIS, InvalidBulletin, bra_to_caaml
from c2corg_api.caching import cache_avalanche_bulletin

log = logging.getLogger(__name__)

API_URL = 'https://public-api.meteofrance.fr/public/DPBRA/v1/massif/BRA'

# the massifs of GET /liste-massifs: Andorra (71) has its own service
MASSIFS = frozenset([*range(1, 24), 40, 41, *range(64, 71), 72, 73, 74])

# Météo-France publishes at about 16:00, and corrects rarely
PUBLICATION = (time(15, 30), time(18, 30))
EXPIRATION_AT_PUBLICATION = 600
EXPIRATION = 3600

# below the 15 s of the lock of the cache (caching.configure_caches): a
# longer fetch would lose the lock, and the cache be taken as down
TIMEOUT = (3, 10)


class UpstreamError(Exception):
    """Météo-France did not answer, or the API key is not set."""


def massif_of(region_id):
    """Return the massif of an EAWS region id (FR-03: 3), None if unknown."""
    if not region_id.startswith('FR-'):
        return None
    try:
        massif = int(region_id[3:])
    except ValueError:
        return None
    return massif if massif in MASSIFS else None


def bulletin(massif):
    """Return the CAAML bulletins of a massif: none out of season."""

    def fetch():
        xml = _fetch(massif, 'xml')
        if not xml:
            return {'bulletins': []}
        try:
            return bra_to_caaml(xml)
        except InvalidBulletin as e:
            raise UpstreamError(f'invalid bulletin of massif {massif}: {e}') from e

    return _cached(str(massif), fetch)


def pdf(massif):
    """Return the official PDF of the bulletin of a massif, None without one."""
    return _cached(f'{massif}.pdf', lambda: _fetch(massif, 'pdf'))


def expiration(now=None):
    """Return how long a bulletin is kept (s): less around its publication."""
    now = (now or datetime.now(PARIS)).astimezone(PARIS).time()
    start, end = PUBLICATION
    return EXPIRATION_AT_PUBLICATION if start <= now <= end else EXPIRATION


def _cached(key, fetch):
    key = f'{caching.CACHE_VERSION}:{key}'
    try:
        return caching.get_or_create(
            cache_avalanche_bulletin, key, fetch, expiration_time=expiration()
        )
    except UpstreamError:
        stale = caching.get(cache_avalanche_bulletin, key)
        if stale is NO_VALUE:
            raise
        log.warning('Météo-France did not answer, answering the last bulletin %s', key)
        return stale


def _fetch(massif, kind):
    # the content, None when there is no bulletin (HTTP 404 "no matching blob")
    key = os.getenv('METEOFRANCE_API_KEY')
    if not key:
        raise UpstreamError('METEOFRANCE_API_KEY is not set')
    try:
        response = requests.get(
            API_URL,
            params={'id-massif': massif, 'format': kind},
            headers={'apikey': key},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise UpstreamError(str(e)) from e
    if response.status_code == 404:
        return None
    if not response.ok:
        raise UpstreamError(f'Météo-France answered {response.status_code}')
    return response.content
