"""The latest avalanche bulletins of an EAWS region, whatever its service."""

from datetime import datetime, timedelta

from c2corg_api.avalanche_bulletins import caaml, meteofrance
from c2corg_api.avalanche_bulletins.cache import CET

# out of season, the latest file of a service keeps the last bulletin of the
# previous season: older than that, it is not shown (as Yeti does)
STALE_AFTER = timedelta(days=2)


class UnknownRegion(Exception):
    """No service c2c reads publishes bulletins for this region."""


def latest_bulletins(region_id, lang):
    """Return the latest bulletins covering a region (or its sub-regions)."""
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


def _now():
    return datetime.now(CET)


def _covers(bulletin, region_id):
    return any(
        r['regionID'] == region_id or r['regionID'].startswith(f'{region_id}-')
        for r in bulletin['regions']
    )


def _end(bulletin):
    return datetime.fromisoformat(bulletin['validTime']['endTime'])
