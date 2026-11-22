"""The avalanche bulletins of Météo-France (DPBRA API), cached in Redis."""
# Fetched on demand, with the key of the association (METEOFRANCE_API_KEY).

import os

import requests

from c2corg_api.avalanche_bulletins.bra import InvalidBulletin, bra_to_caaml
from c2corg_api.avalanche_bulletins.cache import (
    TIMEOUT,
    USER_AGENT,
    UpstreamError,
    cached,
)

API_URL = 'https://public-api.meteofrance.fr/public/DPBRA/v1/massif/BRA'

# the massifs of GET /liste-massifs: Andorra (71) has its own service
MASSIFS = frozenset([*range(1, 24), 40, 41, *range(64, 71), 72, 73, 74])


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

    return cached(f'meteofrance:{massif}', fetch)


def pdf(massif):
    """Return the official PDF of the bulletin of a massif, None without one."""
    return cached(f'meteofrance:{massif}.pdf', lambda: _fetch(massif, 'pdf'))


def _fetch(massif, kind):
    # the content, None when there is no bulletin (HTTP 404 "no matching blob")
    key = os.getenv('METEOFRANCE_API_KEY')
    if not key:
        raise UpstreamError('METEOFRANCE_API_KEY is not set')
    try:
        response = requests.get(
            API_URL,
            params={'id-massif': massif, 'format': kind},
            headers={'apikey': key, 'User-Agent': USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise UpstreamError(str(e)) from e
    if response.status_code == 404:
        return None
    if not response.ok:
        raise UpstreamError(f'Météo-France answered {response.status_code}')
    return response.content
