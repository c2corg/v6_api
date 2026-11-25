"""The avalanche bulletins of Météo-France (DPBRA API), cached in Redis."""
# Fetched on demand, with the key of the association (METEOFRANCE_API_KEY),
# and harvested (avalanche_bulletins.harvesters) with the same requests.

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
    return cached(
        f'meteofrance:{massif}',
        lambda: {'bulletins': parse(_fetch(massif, 'xml'), massif)},
    )


def parse(xml, massif):
    """Return the CAAML bulletins of the XML of a massif (None: no bulletin)."""
    if not xml:
        return []
    try:
        return bra_to_caaml(xml)['bulletins']
    except InvalidBulletin as e:
        raise UpstreamError(f'invalid bulletin of massif {massif}: {e}') from e


def pdf(massif):
    """Return the official PDF of the bulletin of a massif, None without one."""
    return cached(f'meteofrance:{massif}.pdf', lambda: _fetch(massif, 'pdf'))


def _fetch(massif, kind):
    # the content, None when there is no bulletin (HTTP 404 "no matching blob")
    response = request(massif, kind)
    return None if response.status_code == 404 else response.content


def request(massif, kind, headers=None):
    """GET the bulletin of a massif: an answer 2xx, 304 or 404 (no bulletin)."""
    key = os.getenv('METEOFRANCE_API_KEY')
    if not key:
        raise UpstreamError('METEOFRANCE_API_KEY is not set')
    try:
        response = requests.get(
            API_URL,
            params={'id-massif': massif, 'format': kind},
            headers={**(headers or {}), 'apikey': key, 'User-Agent': USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise UpstreamError(str(e)) from e
    if response.status_code not in (304, 404) and not response.ok:
        raise UpstreamError(f'Météo-France answered {response.status_code}')
    return response
