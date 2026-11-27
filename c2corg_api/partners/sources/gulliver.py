"""gulliver.it: the trip reports of the WordPress API of the site (design 5-6).

Real format (recorded 2026-11-27, see the fixtures README):

- `mobile/commentglobal?page=N`: an object keyed by report id (`{"350636":
  {...}}`, key order = sort order), `[]` past the end; 30 reports a page, every
  activity, sorted by OUTING date (`comment_date`, a day, no time zone) with many
  ties: the pages overlap and skip reports, about a quarter of the reports of the
  last days never show up in them.
- `front_page/comments?sorting=id`: the HTML fragment of the home page with the
  50 most recently POSTED reports (the site's own script asks for it); the link of
  each report ends with `/<yyyy>/<mm>/<dd>/<id>/`. It catches the reports the
  paging skips and the ones posted late about an older outing.
- `mobile/comments?id=<report id>`: one report, with a summary of its route.
- `mobile/routes?id=<route id>`: the route (title, region, start point, grade,
  exposure), an object keyed by route id; an unknown id answers 200 with an empty
  skeleton (title "").

Discovery: commentglobal pages 1..MAX_PAGES (until a page ends before `since`),
then the front page fragment: its reports not seen in the pages, dated from
`since - LOOKBACK_DAYS`, are read with `comments?id=` (at most
MAX_REPORT_FETCHES a run). Every report read (pages and details) is kept in the
lookup cache as `report:<id>`, so that a later run never asks for it again.
The routes are cached (`route:<id>`, the extracted fields only), at most
MAX_ROUTE_FETCHES new ones a run, those of the ski reports first. The job
upserts: seeing a report twice is harmless.

The free texts of a report (narrative, access, observations, snow, equipment)
go to `HarvestedOuting.texts` (stored, never served); a recording redacts them
(`REDACT_PATHS`). The first GPX track of a report gives `gpx_url` (a link).
"""

import datetime
import logging
import re
from collections import Counter
from typing import ClassVar
from urllib.parse import urlsplit

from c2corg_api.partners import htmlparse, normalise
from c2corg_api.partners.adapter import ParseError
from c2corg_api.partners.lookups import LookupRequests
from c2corg_api.partners.model import (
    TEXT_MAX_LENGTH,
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

SITE = 'https://www.gulliver.it'
API = f'{SITE}/wp-json/gulliver'
BASE_URL = f'{API}/mobile'
FRONT_PAGE_URL = f'{API}/front_page/comments'
TIMEZONE = 'Europe/Rome'
MAX_PAGES = 5
MAX_REPORT_FETCHES = 15  # `comments?id=` requests per run
MAX_ROUTE_FETCHES = 24  # new route requests per run
# reports are taken this many days before `since`: a report posted late about
# an older outing is not lost (the job upserts)
LOOKBACK_DAYS = 7
GPX_HOSTS = frozenset({'www.gulliver.it', 'gulliver.it'})
FRONT_PAGE_LINK = 'a.btn-ghost[href*="/itinerari/"]'

_INT = re.compile(r'^-?\d+$')
_REPORT_LINK = re.compile(r'/(\d{4})/(\d{2})/(\d{2})/(\d+)/?$')
_COUNTRY = re.compile(r'\(([A-Z]{2})\)\s*$')
# the exposure of a route, in Italian ("Varie", "Tutte": no orientation)
_EXPOSURES = {
    'nord': 'N',
    'nord-est': 'NE',
    'nordest': 'NE',
    'est': 'E',
    'sud-est': 'SE',
    'sudest': 'SE',
    'sud': 'S',
    'sud-ovest': 'SW',
    'sudovest': 'SW',
    'ovest': 'W',
    'nord-ovest': 'NW',
    'nordovest': 'NW',
}
_EXPOSURE_SEP = re.compile(r'\s*(?:[,;/]|\be\b)\s*')

_UNRESOLVED = object()  # in-run marker: this route could not be looked up

# the paths read from a report, in commentglobal and comments?id=
_REPORT_PATHS = [
    'ID',
    'comment_date',
    'comment_post_ID',
    'permalink',
    'term.code',
    'user_nicename',
    'tracks[].guid',
    'content',
    'meta.access.value',
    'meta.obs.value',
    'meta.snow_top.value',
    'meta.snow_low.value',
    'meta.snow_alt.value',
    'meta.skimo_equip.value',
]
# the free texts among them
_REPORT_TEXTS = [
    'content',
    'meta.access.value',
    'meta.obs.value',
    'meta.snow_top.value',
    'meta.snow_low.value',
    'meta.skimo_equip.value',
]


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


def _dict(value):
    return value if isinstance(value, dict) else {}


def _meta_value(meta, key):
    """Return `meta[key].value` (the `{label, value}` objects of the site)."""
    field = _dict(meta).get(key)
    return field.get('value') if isinstance(field, dict) else field


def _first(data, key=None):
    """Return the item of an object keyed by id (`key`, else the first one)."""
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    if not isinstance(data, dict):
        return None
    if key is not None and isinstance(data.get(str(key)), dict):
        return data[str(key)]
    for value in data.values():
        if isinstance(value, dict):
            return value
    return None


def title_from_slug(permalink):
    """Return a title from '.../itinerari/cima-bianca/2026/11/26/350636/'.

    The trailing date and id segments of a report link are skipped.
    """
    if not isinstance(permalink, str):
        return ''
    segments = [s for s in urlsplit(permalink).path.split('/') if s]
    while segments and segments[-1].isdigit():
        segments.pop()
    slug = segments[-1] if segments else ''
    if slug == 'itinerari':
        return ''
    text = normalise.clean_text(slug.replace('-', ' ').replace('_', ' '), 300)
    return text[:1].upper() + text[1:]


def gpx_url(tracks):
    """Return the URL of the first GPX track of a report, if it is a sound one.

    https only, on gulliver.it, a `.gpx` path, at most 500 characters.
    """
    if not isinstance(tracks, list) or not tracks:
        return None
    track = tracks[0]
    url = _text(track.get('guid')) if isinstance(track, dict) else None
    if url is None:
        return None
    url = url.strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme == 'https'
        and (parts.hostname or '').lower() in GPX_HOSTS
        and parts.path.lower().endswith('.gpx')
        and not parts.username
        and port is None
        and len(url) <= 500
    ):
        return url
    return None


def exposures(raw):
    """Return the orientations of 'Nord-Est', 'Sud, Ovest'...; () for Varie/Tutte."""
    text = _text(raw)
    if text is None:
        return ()
    result: list[str] = []
    for part in _EXPOSURE_SEP.split(text.strip().lower()):
        part = re.sub(r'\s*-\s*', '-', part.strip())
        found = _EXPOSURES.get(part)
        values = (found,) if found else normalise.orientations(part)
        for value in values:
            if value not in result:
                result.append(value)
    return tuple(result)


def extract_route(data, route_id=None):
    """Return the dict to cache for a `routes?id=` answer, None if unusable.

    An empty skeleton (unknown id: no title, no position) is `{'empty': True}`,
    cached too, so that it is not asked again on every run.
    """
    route = _first(data, route_id)
    if route is None:
        return None
    meta = _dict(route.get('meta'))
    info = _dict(meta.get('data'))
    coords = _dict(_meta_value(_dict(meta.get('geo')), 'coords'))
    lat, lng = _float(coords.get('lat')), _float(coords.get('lng'))
    if not normalise.valid_lonlat(lng, lat):
        lat = lng = None
    title = route.get('title')
    if isinstance(title, dict):  # WordPress {'rendered': ...}
        title = title.get('rendered')
    title = normalise.clean_text(_text(title), 300) or None
    if title is None and lat is None:
        return {'empty': True}
    region = route.get('region')
    return {
        'title': title,
        'region': _text(region.get('name') if isinstance(region, dict) else None),
        'district': _text(route.get('district')),
        'lat': lat,
        'lng': lng,
        'alt_top': _int(_meta_value(info, 'alt_top')),
        'drop': _int(_meta_value(info, 'drop')),
        'exposure': _text(_meta_value(info, 'exposure')),
        'grade_skimo': _text(_meta_value(info, 'grade_skimo')),
        'grade_skisteep': _text(_meta_value(info, 'grade_skisteep')),
    }


def _texts(content, meta):
    texts = {}

    def put(kind, value):
        text = normalise.clean_text(_text(value), TEXT_MAX_LENGTH)
        if text:
            texts[kind] = text

    put('narrative', content)
    put('access', _meta_value(meta, 'access'))
    put('conditions', _meta_value(meta, 'obs'))
    top = normalise.clean_text(_text(_meta_value(meta, 'snow_top')), 200)
    low = normalise.clean_text(_text(_meta_value(meta, 'snow_low')), 200)
    put(
        'snow',
        '; '.join(p for p in (top and f'top: {top}', low and f'bottom: {low}') if p),
    )
    put('equipment', _meta_value(meta, 'skimo_equip'))
    return texts or None


def slim_report(comment):
    """Return the fields of a report the adapter uses (also its cache entry).

    Raises KeyError, TypeError or ValueError when a mandatory field is wrong.
    """
    if not isinstance(comment, dict):
        raise TypeError('not an object')
    external_id = str(comment['ID']).strip()
    if not external_id:
        raise ValueError('no id')
    meta = _dict(comment.get('meta'))
    term = comment.get('term')
    route = _dict(comment.get('route'))
    region = route.get('region')
    return {
        'id': external_id,
        'date': comment['comment_date'],
        'route_id': comment.get('comment_post_ID'),
        'permalink': comment['permalink'],
        'code': term.get('code') if isinstance(term, dict) else term,
        'author': _text(comment.get('user_nicename')),
        'gpx_url': gpx_url(comment.get('tracks')),
        'snow_alt': _meta_value(meta, 'snow_alt'),
        'texts': _texts(comment.get('content'), meta),
        'route_title': _text(route.get('title')),
        'route_region': _text(region.get('name') if isinstance(region, dict) else None),
        'route_district': _text(route.get('district')),
    }


def front_page_reports(data):
    """Return `[(id, date), ...]` of the report links of the front page fragment."""
    content = data.get('content') if isinstance(data, dict) else None
    if not isinstance(content, str):
        raise ValueError('no content')
    found: dict[str, datetime.date] = {}
    for link in htmlparse.parse(content).select(FRONT_PAGE_LINK):
        match = _REPORT_LINK.search(urlsplit(str(link.get('href', ''))).path)
        if not match:
            continue
        year, month, day, report_id = match.groups()
        try:
            found.setdefault(report_id, datetime.date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return list(found.items())


def _country(region_name):
    """ISO code of a gulliver region: '... (FR)' -> 'FR', an Italian one -> 'IT'."""
    if not region_name:
        return None
    match = _COUNTRY.search(region_name)
    return match.group(1) if match else 'IT'


class GulliverAdapter:
    name = 'gulliver'
    site_name = 'gulliver.it'
    site_url = SITE
    required_secrets = ()
    # the licence of the GPX tracks of the reports (with their author and
    # the site as credit): the job reads them (partner_tracks), the API serves
    # them with it
    TRACK_LICENCE = 'CC BY-NC-ND'
    # 5 pages + 1 front page + 15 reports + 24 routes = 45 at most
    rate = RateLimit(2.0, 45, 20)
    # two endpoints end with `/comments`
    ENDPOINTS: ClassVar[dict[str, str]] = {
        '/front_page/comments': 'front_page_comments'
    }
    # file stem (endpoint) -> EVERY JSON path read from it (`[]` = list items,
    # `*` = any key of an object keyed by ids). Checked by `python -m
    # c2corg_api.partners shapes` and the live tests, and the allow-list of
    # what a recording keeps: anything else (media, the other fields of the
    # tracks...) is never written to a fixture.
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {
        'commentglobal': [f'*.{p}' for p in _REPORT_PATHS],
        'comments': [f'*.{p}' for p in _REPORT_PATHS]
        + ['*.route.title', '*.route.region.name', '*.route.district'],
        'routes': [
            '*.title',
            '*.region.name',
            '*.district',
            '*.meta.data.alt_top.value',
            '*.meta.data.drop.value',
            '*.meta.data.exposure.value',
            '*.meta.data.grade_skimo.value',
            '*.meta.data.grade_skisteep.value',
            '*.meta.geo.coords.value.lat',
            '*.meta.geo.coords.value.lng',
        ],
        # an HTML fragment in a JSON string: trimmed to EMBEDDED_HTML
        'front_page_comments': ['content'],
    }
    EMBEDDED_HTML: ClassVar[dict[str, dict[str, list[str]]]] = {
        'front_page_comments': {'content': [FRONT_PAGE_LINK]}
    }
    # see SkitourAdapter.PSEUDONYMISE_PATHS
    PSEUDONYMISE_PATHS: ClassVar[dict[str, list[str]]] = {
        'commentglobal': ['*.user_nicename'],
        'comments': ['*.user_nicename'],
    }
    # the free texts: read and stored (never served), `[text N chars]` in a
    # recording
    REDACT_PATHS: ClassVar[dict[str, list[str]]] = {
        'commentglobal': [f'*.{p}' for p in _REPORT_TEXTS],
        'comments': [f'*.{p}' for p in _REPORT_TEXTS],
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        _Run(ctx, result).harvest()
        # no cursor: the lookup cache remembers the reports already read
        return result


class _Run:
    def __init__(self, ctx, result):
        self.ctx = ctx
        self.result = result
        self.floor = ctx.since - datetime.timedelta(days=LOOKBACK_DAYS)
        self.seen = set()
        self.routes = {}  # in-run: route id -> dict, or _UNRESOLVED
        self.route_fetches = 0
        self.report_fetches = 0
        self.requests = LookupRequests(ctx, result)
        self.pending = []  # (slim report, date) of the reports to turn into outings

    def harvest(self):
        self._discover()
        # the routes of the ski reports are looked up first: the budget of
        # route requests goes where the conditions matter most
        for report, _ in self.pending:
            mapped = normalise.map_activity('gulliver', report.get('code'))
            if mapped and 'skitouring' in mapped[0]:
                try:
                    self._route(report.get('route_id'))
                except ValueError:
                    pass  # counted when its outing is built
        for report, date in self.pending:
            try:
                outing = self._outing(report, date)
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                self.result.item_errors += 1
                log.warning(
                    'gulliver report %s: %s: %s', report.get('id'), type(e).__name__, e
                )
                continue
            if outing is not None:
                self.result.outings.append(outing)

    def _discover(self):
        for page in range(1, MAX_PAGES + 1):
            comments = self._page(page)
            if not comments:
                break
            oldest = None
            for comment in comments:
                date = self._listed(comment)
                if date is not None and (oldest is None or date < oldest):
                    oldest = date
            if oldest is not None and oldest < self.ctx.since:
                break
        self._front_page()

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
        if isinstance(data, list):  # `[]` past the end
            return data
        if not isinstance(data, dict):
            raise ParseError(f'commentglobal page {page}: not an object')
        return list(data.values())

    def _listed(self, comment):
        """Handle a report of a list; return its date (None if it has none)."""
        try:
            report = slim_report(comment)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            external_id = comment.get('ID') if isinstance(comment, dict) else None
            self.result.item_errors += 1
            log.warning('gulliver report %s: %s: %s', external_id, type(e).__name__, e)
            return None
        date = self._report(report)
        if date is not None and date >= self.floor:
            # a later run that pages less deep finds it on the front page:
            # no `comments?id=` request for it
            self.ctx.lookups.put(f'report:{report["id"]}', report)
        return date

    def _report(self, report):
        """Keep a slim report for its outing; return its date (None if bad)."""
        try:
            date = normalise.local_date(report['date'], TIMEZONE)
            if report['id'] in self.seen:
                self.result.skipped['duplicate'] += 1
                return date
            self.seen.add(report['id'])
            if date < self.floor:
                self.result.skipped['too_old'] += 1
                return date
            self.pending.append((report, date))
            return date
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            self.result.item_errors += 1
            log.warning(
                'gulliver report %s: %s: %s', report.get('id'), type(e).__name__, e
            )
            return None

    # -- the reports of the front page --------------------------------------

    def _front_page(self):
        if not self.requests.available:
            return
        response = self.requests.get(FRONT_PAGE_URL, params={'sorting': 'id'})
        if response is None:
            return  # lookup_failed is counted: the next run asks again
        try:
            if response.status != 200:
                raise ValueError(f'HTTP {response.status}')
            reports = front_page_reports(response.json())
        except ValueError as e:
            log.warning('gulliver front page unusable: %s', e)
            self.result.skipped['front_page_unusable'] += 1
            return
        for report_id, date in reports:
            if report_id in self.seen:
                continue
            if date < self.floor:
                self.seen.add(report_id)
                self.result.skipped['too_old'] += 1
                continue
            report = self._detail(report_id)
            if report is not None:
                self._report(report)

    def _detail(self, report_id):
        """Return the slim report of `comments?id=`, from the cache if there."""
        key = f'report:{report_id}'
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            return cached if cached.get('id') else None
        if self.report_fetches >= MAX_REPORT_FETCHES or not self.requests.available:
            self.result.skipped['report_lookup_deferred'] += 1
            return None
        self.report_fetches += 1
        response = self.requests.get(f'{BASE_URL}/comments', params={'id': report_id})
        if response is None:
            return None
        try:
            if response.status != 200:
                raise ValueError(f'HTTP {response.status}')
            comment = _first(response.json(), report_id)
            if comment is None or str(comment.get('ID')) != report_id:
                raise ValueError('no such report')
            report = slim_report(comment)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            log.info('gulliver report %s: no usable answer: %s', report_id, e)
            self.result.skipped['report_lookup_empty'] += 1
            self.ctx.lookups.put(key, {'id': None})
            return None
        self.ctx.lookups.put(key, report)
        return report

    # -- the outing ----------------------------------------------------------

    def _outing(self, report, date):
        code = report['code']
        mapped = normalise.map_activity('gulliver', code)
        if mapped is None:
            self.result.skipped[f'unmapped_activity:{code}'] += 1
            return None
        activities, steep = mapped
        permalink = _text(report['permalink'])
        if permalink is None or not permalink.startswith(f'{SITE}/'):
            raise ValueError('no permalink')
        route = self._route(report['route_id'])
        if route is None:
            self.result.skipped['route_lookup_deferred'] += 1
            route = {}
        elif route.get('empty'):
            self.result.skipped['route_empty'] += 1
            route = {}
        region_name = route.get('region') or report.get('route_region')
        district = route.get('district') or report.get('route_district')
        region = ' - '.join(p for p in (region_name, district) if p)
        values = {
            'source': 'gulliver',
            'external_id': report['id'],
            'url': permalink,
            'title': (
                normalise.clean_text(route.get('title'), 300)
                or normalise.clean_text(report.get('route_title'), 300)
                or title_from_slug(permalink)
                or report['id']
            ),
            'date': date,
            'activities': activities,
            'author': normalise.clean_text(report.get('author'), 100) or None,
            'lang': 'it',
            'region': normalise.clean_text(region, 200) or None,
            'country': _country(region_name),
            'source_activity': str(code).strip().lower(),
            'snow': self._snow(report.get('snow_alt')),
            'elevation_max': route.get('alt_top'),
            'height_diff_up': route.get('drop'),
            'orientations': exposures(route.get('exposure')),
            'gpx_url': report.get('gpx_url'),
            'texts': report.get('texts') or None,
        }
        lat, lng = route.get('lat'), route.get('lng')
        if normalise.valid_lonlat(lng, lat):
            values.update(lon=lng, lat=lat, geom_quality='start')
        if 'skitouring' in activities:
            steep = self._ski_grade(route, values) or steep
        values['steep'] = steep
        return HarvestedOuting(**values)

    @staticmethod
    def _ski_grade(route, values):
        """Fill the ski rating of `values`; return whether it is steep skiing.

        `grade_skisteep` is a c2c-like ski rating ('4.1'); `grade_skimo` a
        Blachere grade ('MS', 'BSA', 'OS'...).
        """
        steep_grade = _text(route.get('grade_skisteep'))
        if steep_grade:
            values['rating_raw'] = steep_grade.strip()[:32]
            rating = normalise.ski_rating(steep_grade)
            if rating:
                values.update(
                    ski_rating_min=rating,
                    ski_rating_max=rating,
                    rating_system='c2c_ski',
                )
                return normalise.is_steep_ski(rating)
            return False
        grade = _text(route.get('grade_skimo'))
        if grade:
            values['rating_raw'] = grade.strip()[:32]
            parsed = normalise.blachere(grade)
            if parsed:
                low, high, grade_steep = parsed
                values.update(
                    ski_rating_min=low, ski_rating_max=high, rating_system='blachere'
                )
                return grade_steep
        return False

    @staticmethod
    def _snow(snow_alt):
        """Return the snow line (m); the snow qualities are texts (`texts`)."""
        line = _int(snow_alt)
        return {'line_m': line} if line is not None and 0 < line < 9000 else None

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
        if self.route_fetches >= MAX_ROUTE_FETCHES or not self.requests.available:
            return None  # not remembered: nothing was tried
        self.route_fetches += 1
        response = self.requests.get(f'{BASE_URL}/routes', params={'id': route_id})
        if response is None:  # the site failed for it: asked again next run
            self.routes[route_id] = _UNRESOLVED
            return None
        route = None
        if response.status == 200:
            try:
                route = extract_route(response.json(), route_id)
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
