"""gipfelbuch.ch: the "Verhältnisse" (conditions reports) of Switzerland, Austria...

One listing page (`/verhaeltnisse/uebersicht`, about 66 reports of every
activity, newest first) gives per report: id, date, activity, summit with its
altitude, region and country. There are no coordinates in the listing. The page
of a report carries a map (`#map-container-inner[data-lat][data-lon]`, WGS 84):
it is read once per summit (its name and altitude) and remembered in the
`LookupCache` for good, at most `MAX_DETAIL_FETCHES` new summits per run.

HTML is read by labelled elements (`REQUIRED_SELECTORS`), never by position.
The report text, the route notes and the photos are never read.

The route of a report: the listing gives its name under the summit ("Normalroute
ab PP bei Vordere Fildrich"); the route has an id (`/routen/<id>-<slug>`) only on
the page of a report, which is read once per summit. So a route is keyed by its
names (`name:<summit>|<altitude>|<route>`, folded), and gets the link of its page
when the page read for its summit is about the same route.
"""

import datetime
import hashlib
import logging
import re
from collections import Counter
from typing import ClassVar

from c2corg_api.partners import htmlparse, normalise, places
from c2corg_api.partners.adapter import ParseError
from c2corg_api.partners.lookups import LookupRequests
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

SITE_URL = 'https://www.gipfelbuch.ch'
LIST_URL = f'{SITE_URL}/verhaeltnisse/uebersicht'
ARTICLE = 'article.list-item[id^="conditions"]'
MAX_DETAIL_FETCHES = 15  # new summit pages per run

# 'FL - Liechtenstein', 'CH - Wallis', 'A - Tirol' -> ISO 3166-1 alpha-2
REGION_COUNTRIES = {'CH': 'CH', 'A': 'AT', 'D': 'DE', 'I': 'IT', 'F': 'FR', 'FL': 'LI'}
COUNTRY_NAMES = {
    'schweiz': 'CH',
    'österreich': 'AT',
    'deutschland': 'DE',
    'italien': 'IT',
    'frankreich': 'FR',
    'liechtenstein': 'LI',
}
_REGION_CODE = re.compile(r'^([A-Z]{1,2}) - \S')
_ARTICLE_ID = re.compile(r'^conditions(\d+)$')
_ALTITUDE = re.compile(r'\(\s*(\d{2,4})\s*m\s*\)')
_TOUR_DATE = re.compile(r'Datum Tour:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})')
_DATE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$')
_AUTHOR = re.compile(r'^Autor:\s*')
MAX_ALTITUDE = 9000
ROUTE_LINK = '.page-title h2 a[href^="/routen/"]'
_ROUTE_PATH = re.compile(r'^/routen/(\d+)-')


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def _date(text):
    match = _TOUR_DATE.search(text or '') or _DATE.match((text or '').strip())
    if not match:
        raise ValueError(f'no date in {text!r}')
    day, month, year = (int(g) for g in match.groups())
    return datetime.date(year, month, day)


def split_title(title):
    """Return `(summit name, altitude)` of 'Regenflüeli (1582m)'.

    The altitude is None when the title has none or it is not plausible.
    """
    altitudes = [int(m) for m in _ALTITUDE.findall(title)]
    name = _ALTITUDE.sub('', title).strip(' ,;-')
    altitude = next((a for a in altitudes if 0 < a < MAX_ALTITUDE), None)
    return name or title, altitude


def parse_region(labels):
    """Return `(region, country)` of the texts of the region cells.

    One cell is the region ('CH - Zentralschweiz': its prefix is the country),
    the other the country name ('Schweiz'); both can be empty or generic
    ('Andere Region'). The region keeps its label for the job's region table.
    """
    region = country = None
    for label in labels:
        match = _REGION_CODE.match(label)
        if match:
            region = label
            country = REGION_COUNTRIES.get(match.group(1))
            break
    if country is None:
        for label in labels:
            country = COUNTRY_NAMES.get(label.strip().lower())
            if country:
                break
    return region, country


def summit_key(summit, altitude):
    """Return the lookup key of a summit: 'summit:riedbergerhorn_1787'.

    The same summit read in a hike and in a ski tour is one lookup.
    """
    return f'summit:{_slug(summit)}_{altitude or "x"}'[:128]


def route_key(summit, altitude, route_name):
    """Return the external id of a route: 'name:chemispitz|1814|von der talstation'.

    Folded names (`places.full_key`); a key longer than the column ends with a
    hash of the whole key.
    """
    key = (
        f'name:{places.full_key(summit)}|{altitude or ""}|{places.full_key(route_name)}'
    )
    if len(key) > normalise.ROUTE_ID_MAX_LENGTH:
        digest = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:12]
        key = f'{key[: normalise.ROUTE_ID_MAX_LENGTH - 13]}~{digest}'
    return key


def _page_route(soup):
    """Return `{'url', 'name'}` of the route a report page is about, or None.

    The heading links to the route page; its text is '<summit> (<alt>m):
    <route name>'.
    """
    link = soup.select_one(ROUTE_LINK)
    href = str(link.get('href', '')) if link is not None else ''
    if not _ROUTE_PATH.match(href):
        return None
    text = normalise.clean_text(htmlparse.text_of(link), 300)
    name = text.split(':', 1)[1].strip() if ':' in text else ''
    return {'url': f'{SITE_URL}{href}', 'name': name or None}


def parse_detail(markup):
    """Return `{'lat', 'lon', 'route'}` of a report page (its map), or None.

    None when the page has no map element at all (a layout change or an error
    page); the coordinates are None when the map has none or they are not valid.
    `route` is the route of the report (`_page_route`), when the page links it.
    """
    soup = htmlparse.parse(markup)
    element = soup.select_one('#map-container-inner')
    if element is None:
        return None
    place = {'lat': None, 'lon': None}
    route = _page_route(soup)
    if route is not None:
        place['route'] = route
    try:
        lat = float(element.get('data-lat', ''))
        lon = float(element.get('data-lon', ''))
    except ValueError:
        return place
    if normalise.valid_lonlat(lon, lat):
        place.update(lat=lat, lon=lon)
    return place


class GipfelbuchAdapter:
    name = 'gipfelbuch'
    site_name = 'gipfelbuch.ch'
    site_url = SITE_URL
    required_secrets = ()
    rate = RateLimit(2.0, 1 + MAX_DETAIL_FETCHES + 2, 30)
    # No JSON: HTML endpoints are declared by selector (see `contract.py`):
    # every element the adapter reads, and so the only part of a page that a
    # recording keeps. The report text and the route notes are not in it.
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {}
    REQUIRED_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'uebersicht': [
            f'{ARTICLE} .main-icon i[data-tooltip]',
            f'{ARTICLE} .main-title .main',
            f'{ARTICLE} .main-title .main + div',
            f'{ARTICLE} .regions div',
            f'{ARTICLE} .information .date',
            f'{ARTICLE} .autor-infos span',
        ],
        'detail': ['#map-container-inner', ROUTE_LINK],
    }
    # the author (its text and tooltip): "user1", "user2"... in a recording
    PSEUDONYMISE_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'uebersicht': [f'{ARTICLE} .autor-infos span'],
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        _Run(ctx, result).harvest()
        # the page is the whole window: nothing to resume from
        result.cursor = dict(ctx.cursor) if ctx.cursor else None
        return result


class _Run:
    def __init__(self, ctx, result):
        self.ctx = ctx
        self.result = result
        self.seen = set()
        self.summits = {}  # in-run: key -> dict, or None (no answer)
        self.detail_fetches = 0
        self.requests = LookupRequests(ctx, result)

    def harvest(self):
        response = self.ctx.transport.get(LIST_URL)
        if response.status != 200:
            raise ParseError(f'listing: HTTP {response.status}')
        soup = htmlparse.parse(response.text('utf-8'))
        articles = soup.select(ARTICLE)
        if not articles:
            raise ParseError('listing: no conditions article, the layout changed')
        for article in articles:
            self._article(article)

    def _article(self, article):
        external_id = article.get('id', '')
        try:
            match = _ARTICLE_ID.match(external_id)
            if not match:
                raise ValueError('no report id')
            external_id = match.group(1)
            if external_id in self.seen:
                self.result.skipped['duplicate'] += 1
                return
            self.seen.add(external_id)
            outing = self._outing(article, external_id)
            if outing is not None:
                self.result.outings.append(outing)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            self.result.item_errors += 1
            log.warning(
                'gipfelbuch report %s: %s: %s', external_id, type(e).__name__, e
            )

    def _outing(self, article, external_id):
        url = f'{SITE_URL}/verhaeltnisse/{external_id}'

        date_cell = article.select_one('.information .date')
        date = _date(
            (date_cell.get('data-tooltip') or htmlparse.text_of(date_cell))
            if date_cell
            else ''
        )
        if date < self.ctx.since:
            self.result.skipped['too_old'] += 1
            return None

        code = self._activity_code(article)
        mapped = normalise.map_activity('gipfelbuch', code)
        if mapped is None:
            self.result.skipped[f'unmapped_activity:{code}'] += 1
            return None
        activities, steep = mapped

        title_cell = article.select_one('.main-title .main')
        title = normalise.clean_text(htmlparse.text_of(title_cell), 300)
        if not title:
            raise ValueError('no title')
        summit, altitude = split_title(title)
        region, country = parse_region(
            [htmlparse.text_of(cell) for cell in article.select('.regions div')]
        )
        author_cell = article.select_one('.autor-infos span')
        author = (
            normalise.clean_text(_AUTHOR.sub('', htmlparse.text_of(author_cell)), 100)
            or None
            if author_cell
            else None
        )

        values = {
            'source': 'gipfelbuch',
            'external_id': external_id,
            'url': url,
            'title': title,
            'date': date,
            'activities': activities,
            'author': author,
            'lang': 'de',
            'region': normalise.clean_text(region, 200) or None,
            'source_activity': code,
            'steep': steep,
            'elevation_max': altitude,
            'summit_name': normalise.clean_text(summit, 200) or None,
            'country': country,
        }
        place = self._summit(summit, altitude, url)
        located = place and normalise.valid_lonlat(place.get('lon'), place.get('lat'))
        if located:
            values.update(lon=place['lon'], lat=place['lat'], geom_quality='summit')
        route = self._route(article, values, place)
        if route is not None:
            values['routes'] = (route,)
        return HarvestedOuting(**values)

    @staticmethod
    def _route(article, values, place):
        """Return the route named under the summit in the listing, or None.

        The link of the route page is known when the page read for the summit
        (cached, maybe of another report) is about a route of the same name.
        """
        cell = article.select_one('.main-title .main + div')
        name = normalise.clean_text(htmlparse.text_of(cell), 300) if cell else ''
        summit = values['summit_name']
        if not name or not summit:
            return None
        place = place or {}
        page = place.get('route')
        url = None
        if isinstance(page, dict) and places.full_key(
            page.get('name')
        ) == places.full_key(name):
            url = page.get('url')
        altitude = values['elevation_max']
        return normalise.route(
            route_key(summit, altitude, name),
            f'{summit}: {name}',
            url=url,
            summit_name=summit,
            elevation_max=altitude,
            lon=place.get('lon'),
            lat=place.get('lat'),
            geom_quality='summit',
        )

    @staticmethod
    def _activity_code(article):
        """Return the label of the activity icon ('Skitour' -> 'skitour')."""
        icon = article.select_one('.main-icon i[data-tooltip]')
        return _slug(icon.get('data-tooltip', '')) if icon else 'none'

    def _summit(self, summit, altitude, url):
        """Return the coordinates of the summit of a report, or None for now."""
        key = summit_key(summit, altitude)
        if key in self.summits:
            return self.summits[key]
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            self.summits[key] = cached
            return cached
        if self.detail_fetches >= MAX_DETAIL_FETCHES or not self.requests.available:
            self.result.skipped['summit_lookup_deferred'] += 1
            return None  # not remembered: nothing was tried
        self.detail_fetches += 1
        response = self.requests.get(url)
        if response is None:  # the site failed for it: asked again next run
            return None
        place = parse_detail(response.text('utf-8')) if response.status == 200 else None
        if place is None:
            log.info('gipfelbuch %s: no map (HTTP %s)', url, response.status)
            self.summits[key] = None
            self.result.skipped['summit_lookup_failed'] += 1
            return None
        self.ctx.lookups.put(key, place)  # also "no coordinates": asked once
        self.summits[key] = place
        return place
