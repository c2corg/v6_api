"""skitourenportal.eu: the tour reports of the Tourenforum (Austria).

HTML scraping, no API. The site has one portal page per Bundesland
(`/salzburg`, `/kaernten`...): a table of the latest reports, 16 per page
(`?page=N`, newest first), and a map whose inline script lists a marker
(latitude, longitude) for each tour of the page. A tour page adds nothing
useful (photos, narrative, comments), so only the listing pages are read, and
no text of the reports other than title and author reaches the result.

The listing has no activity (every report is a ski tour), no rating and no
elevation. The position comes from the map marker; a report without a marker
keeps its region (and country AT) for the job to resolve with the static table
`regions/skitourenportal.json`. A title like "Spielmann 3027" or "Hochkönig
2941 m" gives `summit_name` and `elevation_max`.

The parsing reads only what `REQUIRED_SELECTORS` lists, which is also the
allow-list of what a recording keeps (`htmlparse.trim`, see `contract.py`); the
author links (`PSEUDONYMISE_SELECTORS`) are recorded as "user1", "user2"...
"""

import datetime
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urljoin

from c2corg_api.partners import htmlparse, normalise
from c2corg_api.partners.adapter import ParseError
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

BASE_URL = 'https://skitourenportal.eu'
# the portal pages: URL slug -> the region text of its table
STATES = {
    'salzburg': 'Salzburg',
    'oberoesterreich': 'Oberösterreich',
    'niederoesterreich': 'Niederösterreich',
    'kaernten': 'Kärnten',
    'steiermark': 'Steiermark',
}
COUNTRY = 'AT'
MAX_PAGES = 2  # per state: the site is quiet, 16 reports per page

TABLE = 'table.border-collapse'
ROW = f'{TABLE} tbody tr[data-href]'
AUTHOR = f'{ROW} > td:nth-of-type(3) a[href]'
MARKER_SCRIPT = 'script:-soup-contains("clickedTour")'
NEXT_PAGE = 'a[rel="next"]'

_TOUR_ID = re.compile(r'/beitrag/(\d+)/?$')
_DATE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$')
# L.marker([lat, lng]).on('click', ... detail: <id> ...): the tour markers
# (the photo markers have an icon option and no click handler)
_MARKER = re.compile(
    r'L\.marker\(\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]\s*\)'
    r"\s*\.on\(\s*'click'.{0,600}?detail\s*:\s*(\d+)",
    re.S,
)
# "Spielmann 3027", "Hochkönig 2941 m", "Salzburger Hochthron 1.853 m"
_SUMMIT = re.compile(
    r'^(?P<name>[^\W\d_][^\d]{1,79}?)\s+(?P<ele>\d{1,2}\.\d{3}|\d{3,4})\s*(?P<m>m|hm)?$',
    re.I,
)
# where the Alps are: a marker outside is a typo, not a position
LON_RANGE, LAT_RANGE = (5.0, 18.0), (43.5, 49.5)


@dataclass(frozen=True, slots=True)
class Row:
    """One line of the listing table."""

    tour_id: str
    url: str
    date: datetime.date
    region: str
    author: str
    author_url: str | None
    title: str


def summit_hint(title):
    """Return `(summit_name, elevation)` when a title ends with an elevation.

    A bare number is taken for an elevation only from 1000 m and outside the
    years 1990 to 2035 ("Saisonstart 2026"). None when the title has no summit.
    """
    match = _SUMMIT.match(title.strip())
    if not match:
        return None
    ele = int(match['ele'].replace('.', ''))
    if match['m']:
        valid = 300 <= ele <= 4810
    else:
        valid = 1000 <= ele <= 4810 and not 1990 <= ele <= 2035
    name = match['name'].strip(' ,;:-')
    if not valid or not name or name.count(' ') > 5:
        return None
    return name, ele


def parse_listing(text):
    """Parse a portal page: `(rows, markers, has_next)`.

    `markers` maps a tour id to `(lat, lng)`. Raises ParseError when the page
    has no table at all (the site changed, or this is not the listing).
    """
    soup = htmlparse.parse(text)
    if not soup.select_one(TABLE):
        raise ParseError('no listing table')
    rows = soup.select(ROW)
    markers = {}
    for script in soup.select(MARKER_SCRIPT):
        for lat, lng, tour_id in _MARKER.findall(script.get_text()):
            markers[tour_id] = (float(lat), float(lng))
    return rows, markers, soup.select_one(NEXT_PAGE) is not None


def read_row(tr):
    """Read a table row into a `Row`; ValueError when it is not a tour."""
    match = _TOUR_ID.search(tr.get('data-href', ''))
    if not match:
        raise ValueError('no tour id in the link')
    cells = tr.find_all('td', recursive=False)
    if len(cells) < 4:
        raise ValueError(f'{len(cells)} cells')
    date = _DATE.match(htmlparse.text_of(cells[0]))
    if not date:
        raise ValueError(f'bad date {htmlparse.text_of(cells[0])!r}')
    day = datetime.date(int(date[3]), int(date[2]), int(date[1]))
    link = cells[2].select_one('a[href]')
    author = htmlparse.text_of(cells[2])
    return Row(
        tour_id=match[1],
        url=urljoin(BASE_URL + '/', tr['data-href']),
        date=day,
        region=htmlparse.text_of(cells[1]),
        author=author,
        author_url=urljoin(BASE_URL + '/', link['href']) if link else None,
        title=htmlparse.text_of(cells[3]),
    )


class SkitourenportalAdapter:
    name = 'skitourenportal'
    site_name = 'skitourenportal.eu'
    site_url = 'https://skitourenportal.eu'
    required_secrets = ()
    # up to MAX_PAGES pages of each of the 5 states; 3 s between two requests
    rate = RateLimit(3.0, 12, 20)
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {}
    # What the adapter reads from the HTML, by endpoint (the last path segment
    # of the URL: the 5 portal pages look alike). The allow-list of a recording
    # (`htmlparse.trim`), and checked by `python -m c2corg_api.partners shapes`
    # and the live tests: a selector that matched in the fixtures and matches
    # nothing in the live pages means the site changed.
    REQUIRED_SELECTORS: ClassVar[dict[str, list[str]]] = {
        slug: [ROW, f'{ROW} > td:nth-of-type(4)', AUTHOR, MARKER_SCRIPT, NEXT_PAGE]
        for slug in STATES
    }
    # the author (a real name, and its profile link): "user1"... in a recording
    PSEUDONYMISE_SELECTORS: ClassVar[dict[str, list[str]]] = {
        slug: [AUTHOR] for slug in STATES
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        rows: dict[str, Row] = {}
        # the map of a portal page also holds tours listed on another one:
        # a position is looked up among the markers of every page read
        markers: dict[str, tuple[float, float]] = {}
        for slug in STATES:
            for page in range(1, MAX_PAGES + 1):
                oldest, has_next = self._page(ctx, result, rows, markers, slug, page)
                if not has_next or oldest is None or oldest < ctx.since:
                    break
        for tour_id, row in rows.items():
            try:
                result.outings.append(self._outing(row, markers.get(tour_id), result))
            except ValueError as e:
                result.item_errors += 1
                log.warning('skitourenportal %s: %s', tour_id, e)
        if rows:
            result.cursor = {'last_id': max(int(tour_id) for tour_id in rows)}
        else:  # nothing seen: keep the previous cursor
            result.cursor = dict(ctx.cursor) if ctx.cursor else None
        return result

    def _page(self, ctx, result, rows, markers, slug, page):
        """Read a page into `rows` and `markers`; return `(oldest date, has next)`."""
        response = ctx.transport.get(
            f'{BASE_URL}/{slug}', params={'page': page} if page > 1 else None
        )
        if response.status != 200:
            raise ParseError(f'{slug} page {page}: HTTP {response.status}')
        try:
            trs, page_markers, has_next = parse_listing(response.text())
        except ParseError as e:
            raise ParseError(f'{slug} page {page}: {e}') from e
        markers.update(page_markers)
        oldest = None
        for tr in trs:
            try:
                row = read_row(tr)
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                result.item_errors += 1
                log.warning(
                    'skitourenportal %s: %s: %s',
                    tr.get('data-href'),
                    type(e).__name__,
                    e,
                )
                continue
            if oldest is None or row.date < oldest:
                oldest = row.date
            if row.tour_id in rows:
                result.skipped['duplicate'] += 1
            elif row.date < ctx.since:
                result.skipped['too_old'] += 1
            else:
                rows[row.tour_id] = row
        return oldest, has_next

    def _outing(self, row, marker, result):
        title = normalise.clean_text(row.title, 300)
        if not title:
            raise ValueError('no title')
        values = {
            'source': self.name,
            'external_id': row.tour_id,
            'url': row.url,
            'title': title,
            'date': row.date,
            # the site has no activity field: it is a ski touring forum
            'activities': ('skitouring',),
            'author': normalise.clean_text(row.author, 100) or None,
            'author_url': row.author_url,
            'lang': 'de',
            'region': normalise.clean_text(row.region, 200) or None,
            'country': COUNTRY,
        }
        hint = summit_hint(title)
        if hint:
            values['summit_name'], values['elevation_max'] = hint
        if marker is not None:
            lat, lng = marker
            if (
                normalise.valid_lonlat(lng, lat)
                and LON_RANGE[0] <= lng <= LON_RANGE[1]
                and LAT_RANGE[0] <= lat <= LAT_RANGE[1]
            ):
                # a point of the tour: where, exactly, is not told
                values.update(lon=lng, lat=lat, geom_quality='route')
            else:
                result.skipped['bad_coordinates'] += 1
        return HarvestedOuting(**values)
