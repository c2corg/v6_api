"""gulliver.it: the trip reports of the WordPress mobile API (design 5-6).

`commentglobal` lists the latest reports of every activity, newest first;
the route of each report (title, region, start point, grade) comes from
`routes?id=` and is cached by route id in the injected `LookupCache`.
Narrative content and media are never read into the result.
"""

import logging
import re
from collections import Counter
from typing import ClassVar
from urllib.parse import urlsplit

from c2corg_api.partners import normalise
from c2corg_api.partners.adapter import ParseError
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

BASE_URL = 'https://www.gulliver.it/wp-json/gulliver/mobile'
TIMEZONE = 'Europe/Rome'
MAX_PAGES = 5
MAX_ROUTE_FETCHES = 25  # new route requests per run
_INT = re.compile(r'^-?\d+$')

_UNRESOLVED = object()  # in-run marker: this route could not be looked up


def _int(value):
    """Return an int or a string of digits as int, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INT.match(value.strip()):
        return int(value.strip())
    return None


def _float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _text(value):
    """Return the value if it is a non-empty string, else None."""
    return value if isinstance(value, str) and value.strip() else None


def title_from_slug(permalink):
    """Return a readable title from '.../itinerari/cima-bianca-da-cheneil/'."""
    segments = [s for s in urlsplit(permalink).path.split('/') if s]
    slug = segments[-1] if segments else ''
    text = normalise.clean_text(slug.replace('-', ' ').replace('_', ' '), 300)
    return text[:1].upper() + text[1:]


def extract_route(data):
    """Return the dict to cache for a `routes?id=` answer, None if unusable."""
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return None
    meta = data.get('meta') if isinstance(data.get('meta'), dict) else {}
    info = meta.get('data') if isinstance(meta.get('data'), dict) else {}
    geo = meta.get('geo') if isinstance(meta.get('geo'), dict) else {}
    coords = geo.get('coords') if isinstance(geo.get('coords'), dict) else {}
    region = data.get('region')
    region_name = region.get('name') if isinstance(region, dict) else region
    lat, lng = _float(coords.get('lat')), _float(coords.get('lng'))
    if not normalise.valid_lonlat(lng, lat):
        lat = lng = None
    title = data.get('title')
    if isinstance(title, dict):  # WordPress {'rendered': ...}
        title = title.get('rendered')
    return {
        'title': _text(title),
        'region': _text(region_name),
        'district': _text(data.get('district')),
        'lat': lat,
        'lng': lng,
        'alt_top': _int(info.get('alt_top')),
        'drop': _int(info.get('drop')),
        'exposure': _text(info.get('exposure')),
        'grade_skimo': _text(info.get('grade_skimo')),
    }


class GulliverAdapter:
    name = 'gulliver'
    site_name = 'gulliver.it'
    site_url = 'https://www.gulliver.it'
    required_secrets = ()
    rate = RateLimit(2.0, 40, 20)
    # file stem (endpoint) -> EVERY JSON path read from it (`[]` = list items).
    # Checked by `python -m c2corg_api.partners shapes` and the live tests, and
    # the allow-list of what a recording keeps: anything else (comment texts,
    # access and observation notes, tracks...) is never written to a fixture.
    # A path that ends on an object keeps the whole object.
    # see SkitourAdapter.PSEUDONYMISE_PATHS
    PSEUDONYMISE_PATHS: ClassVar[dict[str, list[str]]] = {
        'commentglobal': ['[].user_nicename']
    }

    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {
        'commentglobal': [
            '[].ID',
            '[].comment_date',
            '[].comment_post_ID',
            '[].permalink',
            '[].term',
            '[].user_nicename',
            '[].meta.snow_top',
            '[].meta.snow_low',
            '[].meta.snow_alt',
        ],
        'routes': [
            'title',
            'region',
            'district',
            'meta.data.alt_top',
            'meta.data.drop',
            'meta.data.exposure',
            'meta.data.grade_skimo',
            'meta.geo.coords.lat',
            'meta.geo.coords.lng',
        ],
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        run = _Run(ctx, result)
        run.harvest()
        if run.max_id is not None:
            result.cursor = {'last_comment_id': run.max_id}
        else:  # nothing seen: keep the previous cursor
            result.cursor = dict(ctx.cursor) if ctx.cursor else None
        return result


class _Run:
    def __init__(self, ctx, result):
        self.ctx = ctx
        self.result = result
        self.max_id = None
        self.seen = set()
        self.routes = {}  # in-run: route id -> dict, or _UNRESOLVED
        self.route_fetches = 0

    def harvest(self):
        for page in range(1, MAX_PAGES + 1):
            comments = self._page(page)
            if not comments:
                return
            oldest = None
            for comment in comments:
                date = self._comment(comment)
                if date is not None and (oldest is None or date < oldest):
                    oldest = date
            if oldest is not None and oldest < self.ctx.since:
                return

    def _page(self, page):
        response = self.ctx.transport.get(
            f'{BASE_URL}/commentglobal', params={'page': page}
        )
        if response.status != 200:
            raise ParseError(f'commentglobal page {page}: HTTP {response.status}')
        try:
            data = response.json()
        except ValueError as e:
            raise ParseError(f'commentglobal page {page}: not JSON') from e
        if not isinstance(data, list):
            raise ParseError(f'commentglobal page {page}: not a list')
        return data

    def _comment(self, comment):
        """Handle one comment; return its date (None if it has none)."""
        external_id = None
        try:
            if not isinstance(comment, dict):
                raise ValueError('not an object')
            external_id = str(comment['ID'])
            numeric_id = _int(comment['ID'])
            date = normalise.local_date(comment['comment_date'], TIMEZONE)
            if numeric_id is not None and (
                self.max_id is None or numeric_id > self.max_id
            ):
                self.max_id = numeric_id
            if external_id in self.seen:
                self.result.skipped['duplicate'] += 1
                return date
            self.seen.add(external_id)
            if date < self.ctx.since:
                self.result.skipped['too_old'] += 1
                return date
            outing = self._outing(comment, external_id, date)
            if outing is not None:
                self.result.outings.append(outing)
            return date
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            self.result.item_errors += 1
            log.warning('gulliver comment %s: %s: %s', external_id, type(e).__name__, e)
            return None

    def _outing(self, comment, external_id, date):
        term = comment['term']
        code = term['code'] if isinstance(term, dict) else term
        mapped = normalise.map_activity('gulliver', code)
        if mapped is None:
            self.result.skipped[f'unmapped_activity:{code}'] += 1
            return None
        activities, steep = mapped
        permalink = comment['permalink']
        if not _text(permalink):
            raise ValueError('no permalink')
        route = self._route(comment['comment_post_ID'])
        if route is None:
            self.result.skipped['route_lookup_deferred'] += 1
            route = {}
        values = {
            'source': 'gulliver',
            'external_id': external_id,
            'url': permalink,
            'title': (
                normalise.clean_text(route.get('title'), 300)
                or title_from_slug(permalink)
                or external_id
            ),
            'date': date,
            'activities': activities,
            'author': normalise.clean_text(comment.get('user_nicename'), 100) or None,
            'lang': 'it',
            'region': normalise.clean_text(
                route.get('district') or route.get('region'), 200
            )
            or None,
            'source_activity': str(code).strip().lower(),
            'snow': self._snow(comment.get('meta')),
            'elevation_max': route.get('alt_top'),
            'height_diff_up': route.get('drop'),
            'orientations': normalise.orientations(route.get('exposure')),
        }
        lat, lng = route.get('lat'), route.get('lng')
        if normalise.valid_lonlat(lng, lat):
            values.update(lon=lng, lat=lat, geom_quality='start')
        grade = route.get('grade_skimo')
        if grade and 'skitouring' in activities:
            values['rating_raw'] = grade.strip()
            parsed = normalise.blachere(grade)
            if parsed:
                low, high, grade_steep = parsed
                values.update(
                    ski_rating_min=low,
                    ski_rating_max=high,
                    rating_system='blachere',
                )
                steep = steep or grade_steep
        values['steep'] = steep
        return HarvestedOuting(**values)

    @staticmethod
    def _snow(meta):
        if not isinstance(meta, dict):
            return None
        snow = {}
        for key, field in (
            ('top_cm', 'snow_top'),
            ('low_cm', 'snow_low'),
            ('line_m', 'snow_alt'),
        ):
            value = _int(meta.get(field))
            if value is not None:
                snow[key] = value
        return snow or None

    def _route(self, route_id):
        """Return the route dict, or None when it cannot be had this run."""
        route_id = _int(route_id)
        if route_id is None:
            raise ValueError('bad comment_post_ID')
        if route_id in self.routes:
            found = self.routes[route_id]
            return None if found is _UNRESOLVED else found
        key = f'route:{route_id}'
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            self.routes[route_id] = cached
            return cached
        if self.route_fetches >= MAX_ROUTE_FETCHES:
            return None  # not remembered: nothing was tried
        self.route_fetches += 1
        response = self.ctx.transport.get(f'{BASE_URL}/routes', params={'id': route_id})
        route = None
        if response.status == 200:
            try:
                route = extract_route(response.json())
            except ValueError:
                route = None
        if route is None:
            log.info(
                'gulliver route %s: no usable answer (%s)', route_id, response.status
            )
            self.routes[route_id] = _UNRESOLVED
            return None
        self.ctx.lookups.put(key, route)
        self.routes[route_id] = route
        return route
