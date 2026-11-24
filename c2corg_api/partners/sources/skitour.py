"""skitour.fr: the `/api/sorties` listing (design sections 5 and 6).

Only the structured fields are read. `conditions`, `recit` and `photos` are
under a licence that forbids reusing them out of context, so they are never
looked at.
"""

import logging
import re
from collections import Counter
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from c2corg_api.partners import normalise
from c2corg_api.partners.adapter import ParseError, SourceBlocked, require_secrets
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

API_URL = 'https://skitour.fr/api/sorties'
OUTING_URL = 'https://skitour.fr/sorties/{}'
TIMEZONE = 'Europe/Paris'

# skitour answers HTTP 200 with `{"ERROR": "<message>"}` (observed:
# "NO API KEY", "INVALID API KEY"). A message about the key, the rights or a
# quota means the site refuses us (SourceBlocked, status 'blocked': someone has
# to fix or renew the key). Any other message is an answer we do not know:
# ParseError (status 'failing'), with the message.
_REFUSAL = re.compile(
    r'\b(api|key|cle|clef|auth\w*|token|quota|limit\w*|forbidden|denied|'
    r'unauthori[sz]ed|rate|too many|expired|disabled|banned|blocked)\b',
    re.IGNORECASE,
)


class SkitourAdapter:
    name: ClassVar[str] = 'skitour'
    site_name: ClassVar[str] = 'skitour.fr'
    site_url: ClassVar[str] = 'https://skitour.fr'
    required_secrets: ClassVar[tuple[str, ...]] = ('SKITOUR_API_KEY',)
    # the API allows 60 requests/min and 1000/day
    rate: ClassVar[RateLimit] = RateLimit(1.1, 10, 20)

    # file stem (endpoint) -> EVERY JSON path read from it (`[]` = list items).
    # Checked by `python -m c2corg_api.partners shapes` and the live tests, and
    # the allow-list of what a recording keeps: the licensed texts and photos
    # (`conditions`, `recit`, `photos`) are never listed, so never written.
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {
        'sorties': [
            '[].id',
            '[].titre',
            '[].date',
            '[].auteur.pseudo',
            '[].massif.nom',
            '[].sommets[].altitude',
            '[].sommets[].latlon',
            '[].orientation',
            '[].denivele',
            '[].dif_ski',
        ]
    }

    PAGE_SIZE: ClassVar[int] = 200
    MAX_DAYS: ClassVar[int] = 31

    def fetch(self, ctx: FetchContext) -> FetchResult:
        require_secrets(ctx, self.required_secrets)
        headers = {'cle': ctx.secrets['SKITOUR_API_KEY']}
        days = (ctx.now.astimezone(ZoneInfo(TIMEZONE)).date() - ctx.since).days
        days = min(max(days, 1), self.MAX_DAYS)

        result = FetchResult(outings=[], skipped=Counter())
        last_id = _last_id(ctx.cursor)
        for page in range(1, self.rate.max_requests_per_run + 1):
            response = ctx.transport.get(
                API_URL,
                params={'c': 1, 'l': self.PAGE_SIZE, 'j': days, 'p': page},
                headers=headers,
            )
            items = self._items(response)
            for item in items:
                seen = self._handle(item, ctx, result)
                if seen is not None and (last_id is None or seen > last_id):
                    last_id = seen
            if len(items) < self.PAGE_SIZE:
                break
        # without any id seen, the previous cursor is kept
        if last_id is not None:
            result.cursor = {'last_id': last_id}
        else:
            result.cursor = dict(ctx.cursor) if ctx.cursor else None
        return result

    @staticmethod
    def _items(response) -> list:
        if response.status != 200:
            raise ParseError(f'HTTP {response.status} from {response.url}')
        try:
            payload = response.json()
        except ValueError as e:
            raise ParseError(f'not JSON: {e}') from e
        if isinstance(payload, dict) and 'ERROR' in payload:
            message = normalise.clean_text(str(payload['ERROR']), 200) or '?'
            if _REFUSAL.search(message):
                raise SourceBlocked(f'skitour API error: {message}')
            raise ParseError(f'skitour API error: {message}')
        if not isinstance(payload, list):
            raise ParseError(
                f'expected a list of outings, got {type(payload).__name__}'
            )
        return payload

    def _handle(self, item: Any, ctx: FetchContext, result: FetchResult):
        """Add the item to the result; return its id when it has one."""
        item_id = normalise.to_int(item.get('id')) if isinstance(item, dict) else None
        try:
            outing = self._outing(item, item_id)
        except (KeyError, TypeError, ValueError) as e:
            log.warning('skitour: skipping outing %r: %s', item_id, e)
            result.item_errors += 1
            return item_id
        if outing.date < ctx.since:
            result.skipped['too_old'] += 1
        else:
            result.outings.append(outing)
        return item_id

    def _outing(self, item: Any, item_id: int | None) -> HarvestedOuting:
        if not isinstance(item, dict):
            raise TypeError('outing is not an object')
        if item_id is None:
            raise KeyError('id')
        title = normalise.clean_text(item.get('titre'), 300)
        if not title:
            raise KeyError('titre')
        if item.get('date') is None:
            raise KeyError('date')
        date = normalise.local_date(item['date'], TIMEZONE)

        author = item.get('auteur')
        massif = item.get('massif')
        summits = [s for s in item.get('sommets') or [] if isinstance(s, dict)]
        altitudes = [
            a for a in (normalise.to_int(s.get('altitude')) for s in summits) if a
        ]

        raw_rating = item.get('dif_ski')
        raw_rating = None if raw_rating is None else str(raw_rating).strip() or None
        rating = normalise.ski_rating(raw_rating)

        lon, lat, quality = self._geometry(summits)
        return HarvestedOuting(
            source=self.name,
            external_id=str(item_id),
            url=OUTING_URL.format(item_id),
            title=title,
            date=date,
            activities=('skitouring',),
            author=(
                normalise.clean_text(author.get('pseudo'), 100) or None
                if isinstance(author, dict)
                else None
            ),
            lang='fr',
            region=(
                normalise.clean_text(massif.get('nom'), 200) or None
                if isinstance(massif, dict)
                else None
            ),
            ski_rating_min=rating,
            ski_rating_max=rating,
            rating_raw=raw_rating,
            rating_system='c2c_ski' if rating else None,
            steep=normalise.is_steep_ski(rating),
            elevation_max=max(altitudes) if altitudes else None,
            height_diff_up=normalise.to_int(item.get('denivele')),
            orientations=normalise.orientations(item.get('orientation')),
            lon=lon,
            lat=lat,
            geom_quality=quality,
        )

    @staticmethod
    def _geometry(summits):
        """Return the highest summit with usable coordinates, else no geometry."""
        best = None
        for summit in summits:
            latlon = summit.get('latlon')
            if not isinstance(latlon, list | tuple) or len(latlon) != 2:
                continue
            lat, lon = latlon
            if not normalise.valid_lonlat(lon, lat):
                continue
            altitude = normalise.to_int(summit.get('altitude'))
            altitude = altitude if altitude is not None else -1
            if best is None or altitude > best[0]:
                best = (altitude, lon, lat)
        if best is None:
            return None, None, 'none'
        return best[1], best[2], 'summit'


def _last_id(cursor) -> int | None:
    value = cursor.get('last_id') if cursor else None
    return normalise.to_int(value)
