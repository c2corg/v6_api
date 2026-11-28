"""on-ice.it: the trip reports of an Italian community site (PHP, HTML only).

One list of the latest reports of every type (`onice_reports.php?type=0`, 60
rows a page, the newest submitted first; `&u=0&start=60` is the next page):
date, title, region, height difference and author. A row links to its detail
page (`onice_view_report.php?type=<type>&id=<id>`): the ids are per type, so the
external id is `<type>-<id>`. The type is the activity: 1 ski touring, 2
hiking, 3 rock, 4 ice and mixed, 6 mountain biking (5 and 7 list nothing).

The detail page gives the elevation of the arrival, the grade, the exposure and
the free texts (comment, conditions, snow, avalanche risk, start, gear). It is
fetched at most once per report (the answer is kept in the `LookupCache` under
`report:<type>-<id>`), at most `MAX_DETAIL_FETCHES` times per run, the newest
reports first. The reports over the cap keep what the list gives, and get the
rest on the next runs.

There are no coordinates anywhere on the site (no map, no GPX): an outing has
the hints the job resolves (`summit_name` from the title, `elevation_max`,
`region`, `country`).

The pages are ISO-8859-1, some fields hold UTF-8 bytes (`30Â°`), and the markup
is loose (text after `</html>`, raw `&` in the links): they are decoded by hand
(`decode`, `fix_mojibake`) and parsed with the lenient `html.parser`. A report
that does not exist answers HTTP 200 with a PHP "Fatal error" body: a detail
page without `td.report-title` is taken for gone.

The free texts go to `HarvestedOuting.texts` (stored, never served), and a
recording replaces them by placeholders (`REDACT_SELECTORS`). The photos and the
e-mail of the author (in an HTML comment of the detail page, next to the
author's name) are never read nor recorded: everything is read through CSS
selectors (`REQUIRED_SELECTORS`), the allow-list of a recording.
"""

import datetime
import logging
import re
from collections import Counter
from typing import ClassVar
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4.element import Comment, NavigableString, Tag

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

# https fails (an old TLS setup): plain http only
BASE_URL = 'http://www.on-ice.it/onice/'
LIST_URL = urljoin(BASE_URL, 'onice_reports.php')
DETAIL_URL = urljoin(BASE_URL, 'onice_view_report.php')
PAGE_SIZE = 60
MAX_PAGES = 2
MAX_DETAIL_FETCHES = 15  # new detail pages per run
# the report types of the site -> the activity codes of `normalise.ACTIVITY_MAP`
TYPES = {
    '1': 'scialpinismo',
    '2': 'escursionismo',
    '3': 'roccia',
    '4': 'ghiaccio_misto',
    '6': 'mtb',
}
# "Ghiaccio e misto" holds the alpine routes (summer) and the ice falls
# (winter): a title naming an ice fall makes it ice climbing
_ICE_FALL = re.compile(r'cascat|ice\s*fall|candel', re.I)
# the region of a report: an Italian region, or a country (in Italian)
COUNTRIES = {
    'svizzera': 'CH',
    'francia': 'FR',
    'austria': 'AT',
    'germania': 'DE',
    'slovenia': 'SI',
    'spagna': 'ES',
}
ITALIAN_REGIONS = frozenset(
    {
        "valle d'aosta",
        'piemonte',
        'lombardia',
        'trentino alto adige',
        'veneto',
        'friuli venezia giulia',
        'liguria',
        'emilia romagna',
        'toscana',
        'marche',
        'umbria',
        'lazio',
        'abruzzo',
        'molise',
        'campania',
        'puglia',
        'basilicata',
        'calabria',
        'sicilia',
        'sardegna',
    }
)
# the exposure words of the site (Nord, Sud-Est...): 'Varia' is none
_POINTS = {'nord': 'N', 'sud': 'S', 'est': 'E', 'ovest': 'W'}

_DATE = re.compile(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$')
_NUMBER = re.compile(r'(\d+)')
_HEAD = re.compile(r'\s*(?:,|\s[-–]\s)')
_BRACKETS = re.compile(r'\([^()]*\)?')
# an elevation in a title: '1953 m', '3402m', '2500mt', 'm 2457', 'q. 2080'
_ELEVATION = re.compile(
    r'(?:\b(\d{3,4})\s*m(?:t|etri)?\b|\b(?:m|q)\.?\s*(\d{3,4})\b)', re.I
)
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')

# the report rows: a row (not one of the layout tables around the list)
# holding a link to a report, and its cells
ROW = 'tr:not(:has(tr)):has(a[href*="onice_view_report.php"])'
HEADER = 'tr.header > td'
CELLS = f'{ROW} > td'
AUTHOR = f'{ROW} > td > a.reportlink'
# the detail page: the title, then labelled rows (a label cell, a value cell)
TITLE = 'td.report-title'
LABELS = {
    'elevation': ('Quota arrivo', 'Quota massima'),
    'rating': ('Difficolt',),  # 'Difficoltà', an entity in the page
    'exposure': ('Esposizione',),  # 'in salita', 'in discesa', or alone
}
# the rows holding free text (label, as the page writes it) -> kind of
# `HarvestedOuting.texts`. 'Condizioni' also matches 'Condizioni Salita' and
# 'Condizioni Discesa' (MTB).
TEXT_LABELS = {
    'Commento': 'narrative',
    'Condizioni': 'conditions',
    'Valutazione itinerario': 'conditions',
    'Rischio valanghe': 'conditions',
    'Neve prevalente': 'snow',
    'Altra neve': 'snow',
    'Partenza': 'access',
    'Rifugio di appoggio': 'access',
    'Attrezzatura consigliata': 'equipment',
}
_NOTHING = frozenset({'nessuno', 'nessuna', '-', 'n.d.'})


def _label(*texts):
    """Return the selector of the label cells containing any of the texts."""
    quoted = ', '.join(f'"{text}"' for text in texts)
    return f'td.reportrowlabel:-soup-contains({quoted})'


def _value(*texts):
    """Return the selector of the value cells of those labels."""
    return f'{_label(*texts)} + td'


_READ_LABELS = [text for texts in LABELS.values() for text in texts]
# The rows of a page depend on its type (no snow for a hike, no exposure for
# MTB...): the contract is one selector for all the rows read, so that a run
# of one type only does not look like a change of the site; plus the rows
# every type has.
DETAIL_SELECTORS = [
    TITLE,
    _label('Difficolt'),
    _value('Difficolt'),
    _label('Commento'),
    _value('Commento'),
    _label(*_READ_LABELS, *TEXT_LABELS),
    _value(*_READ_LABELS, *TEXT_LABELS),
]


def decode(body: bytes) -> str:
    """Decode a page: UTF-8 when it is (a recording), else Windows-1252.

    The site sends ISO-8859-1; Windows-1252 is the same where it matters, and
    also reads the typographic quotes the old forms let in.
    """
    try:
        return body.decode('utf-8')
    except UnicodeDecodeError:
        return body.decode('cp1252', errors='replace')


def fix_mojibake(text: str) -> str:
    """Re-decode a field that holds UTF-8 bytes read as Latin-1 ('30Â°' -> '30°')."""
    if not text or not any(c in text for c in 'ÂÃ'):
        return text
    try:
        return text.encode('cp1252').decode('utf-8')
    except UnicodeError:
        return text


def _text(node):
    return fix_mojibake(htmlparse.text_of(node))


def _int(text):
    match = _NUMBER.search(text or '')
    return int(match.group(1)) if match else None


def country_of(region):
    """Return the ISO country of a region text, None when unknown ('Altro')."""
    key = (region or '').strip().lower()
    if key in ITALIAN_REGIONS:
        return 'IT'
    return COUNTRIES.get(key)


def orientations(values):
    """Return the c2c orientations of 'Sud-Est', 'Nord'... ('Varia' is none)."""
    codes = []
    for value in values:
        words = [w for w in re.split(r'[-\s/]+', value.strip().lower()) if w]
        if words and all(w in _POINTS for w in words):
            codes.append(''.join(_POINTS[w] for w in words))
    return normalise.orientations(codes)


def summit_hint(title):
    """Return `(summit_name, elevation)` of a title, either may be None.

    The summit is the head of the title, before a comma or a dash ('Mont
    Miravidi, dal Lago Verney'), without its brackets and its elevation
    ('Monte Guglielmo 1953 m'). The job matches it against the c2c summits by
    name: a head that names no summit just finds nothing.
    """
    head = _HEAD.split(title, maxsplit=1)[0]
    match = _ELEVATION.search(head)
    elevation = None
    if match:
        value = int(match.group(1) or match.group(2))
        elevation = value if 300 <= value <= 4810 else None
        head = head[: match.start()] + head[match.end() :]
    name = normalise.clean_text(_BRACKETS.sub(' ', head), 200).strip(' ,;:-.')
    if not re.search(r'[^\W\d_]{2}', name) or len(name) > 60:
        name = None
    return name, elevation


class OniceAdapter:
    name = 'onice'
    site_name = 'on-ice.it'
    site_url = BASE_URL
    required_secrets = ()
    # no robots.txt: 2 s between two requests, as for the other small sites
    rate = RateLimit(2.0, MAX_PAGES + MAX_DETAIL_FETCHES, 30)
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {}
    # endpoint -> every CSS selector read from it (`contract.py`): the check of
    # the live shapes, and the allow-list of what a recording keeps. Not the
    # photos, nor the author row of a detail page (its e-mail comment).
    REQUIRED_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'onice_reports': [HEADER, CELLS, AUTHOR],
        'onice_view_report': DETAIL_SELECTORS,
    }
    # the author (a user name, and its profile link): "user1"... in a recording
    PSEUDONYMISE_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'onice_reports': [AUTHOR],
    }
    # the free texts: read and stored (never served), `[text N chars]` in a
    # recording
    REDACT_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'onice_view_report': [_value(*TEXT_LABELS)],
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        _Run(ctx, result).harvest()
        # no cursor: the lookup cache remembers the reports already read
        return result


class _Run:
    def __init__(self, ctx, result):
        # the cap of a run (the temporary backfill sets its own)
        self.max_detail_fetches = MAX_DETAIL_FETCHES
        self.ctx = ctx
        self.result = result
        self.seen = set()
        self.detail_fetches = 0
        self.requests = LookupRequests(ctx, result)

    def harvest(self):
        drafts = []
        for page in range(MAX_PAGES):
            page_drafts, rows = self._list(page)
            drafts.extend(page_drafts)
            # the next page only while the list is new to us: a full page whose
            # oldest report of the period has never been looked up
            if rows < PAGE_SIZE or not page_drafts:
                break
            if self.ctx.lookups.get(_key(page_drafts[-1])) is not None:
                break
        for draft in drafts:
            self.result.outings.append(self._outing(draft))

    # -- the list ----------------------------------------------------------

    def _list(self, page):
        """Return the drafts of a page of the list, and its number of rows."""
        params = {'type': 0}
        if page:
            params.update(u=0, start=page * PAGE_SIZE)
        response = self.ctx.transport.get(LIST_URL, params=params)
        if response.status != 200:
            raise ParseError(f'onice_reports page {page + 1}: HTTP {response.status}')
        soup = htmlparse.parse(decode(response.body))
        columns = {
            _text(td).lower().rstrip('.'): i for i, td in enumerate(soup.select(HEADER))
        }
        if not {'data', 'gita'} <= set(columns):
            raise ParseError(f'onice_reports page {page + 1}: no list in the page')
        rows = soup.select(ROW)
        drafts = []
        for tr in rows:
            draft = self._row(tr, columns)
            if draft is not None:
                drafts.append(draft)
        return drafts, len(rows)

    def _row(self, tr, columns):
        """Return the values of a row of the list (None: skipped or broken)."""
        external_id = None
        try:
            cells = tr.find_all('td', recursive=False)

            def cell(name):
                index = columns.get(name)
                return (
                    cells[index] if index is not None and index < len(cells) else None
                )

            link = cell('gita').select_one('a[href*="onice_view_report.php"]')
            query = parse_qs(urlsplit(link.get('href', '')).query)
            report_type = query.get('type', [''])[0]
            report_id = query.get('id', [''])[0]
            if not (report_type.isdigit() and report_id.isdigit()):
                raise ValueError(f'bad report link {link.get("href")!r}')
            external_id = f'{report_type}-{report_id}'
            if external_id in self.seen:
                self.result.skipped['duplicate'] += 1
                return None
            self.seen.add(external_id)
            code = TYPES.get(report_type)
            mapped = normalise.map_activity('onice', code) if code else None
            if mapped is None:
                self.result.skipped[f'unmapped_activity:{report_type}'] += 1
                return None
            match = _DATE.match(_text(cell('data')))
            if match is None:
                raise ValueError(f'bad date {_text(cell("data"))!r}')
            day, month, year = (int(g) for g in match.groups())
            date = datetime.date(year, month, day)
            if date < self.ctx.since:
                self.result.skipped['too_old'] += 1
                return None
            title = normalise.clean_text(_text(link), 300)
            if not title:
                raise ValueError('no title')
            activities, steep = mapped
            if code == 'ghiaccio_misto' and _ICE_FALL.search(title):
                activities = ('ice_climbing',)
            region = normalise.clean_text(_text(cell('regione')), 200) or None
            values = {
                'source': 'onice',
                'external_id': external_id,
                'url': f'{DETAIL_URL}?type={report_type}&id={report_id}',
                'title': title,
                'date': date,
                'activities': activities,
                'steep': steep,
                'lang': 'it',
                'region': region,
                'country': country_of(region),
                'source_activity': code,
                'height_diff_up': _int(_text(cell('disl'))) or None,
            }
            summit, elevation = summit_hint(title)
            if summit:
                values['summit_name'] = summit
            if elevation:
                values['elevation_max'] = elevation
            author = cell('onicer')
            author_link = author.select_one('a[href]') if author else None
            if author is not None:
                values['author'] = normalise.clean_text(_text(author), 100) or None
            if author_link is not None:
                values['author_url'] = urljoin(BASE_URL, author_link['href'])
            return values
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            self.result.item_errors += 1
            log.warning('onice report %s: %s: %s', external_id, type(e).__name__, e)
            return None

    # -- the detail pages --------------------------------------------------

    def _outing(self, values):
        detail = self._detail(values)
        if detail is None:
            self.result.skipped['detail_deferred'] += 1
        elif detail.get('gone'):
            self.result.skipped['detail_gone'] += 1
        else:
            if detail.get('elevation'):
                values['elevation_max'] = detail['elevation']
            if detail.get('orientations'):
                values['orientations'] = tuple(detail['orientations'])
            values['texts'] = detail.get('texts') or None
            rating = detail.get('rating')
            if rating:
                values['rating_raw'] = rating[:50]
                parsed = normalise.blachere(rating)
                if parsed and 'skitouring' in values['activities']:
                    low, high, steep = parsed
                    values.update(
                        ski_rating_min=low,
                        ski_rating_max=high,
                        rating_system='blachere',
                        steep=values['steep'] or steep,
                    )
        return HarvestedOuting(**values)

    def _detail(self, values):
        """Return the dict of a detail page, None when it cannot be had this run."""
        key = _key(values)
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            return cached
        if (
            self.detail_fetches >= self.max_detail_fetches
            or not self.requests.available
        ):
            return None  # not remembered: nothing was tried
        self.detail_fetches += 1
        report_type, report_id = values['external_id'].split('-')
        response = self.requests.get(
            DETAIL_URL, params={'type': report_type, 'id': report_id}
        )
        if response is None:  # the site failed for it: asked again next run
            return None
        if response.status == 404:
            detail = {'gone': True}
        elif response.status == 200:
            detail = extract_detail(decode(response.body))
        else:
            log.info('onice report %s: HTTP %s', values['external_id'], response.status)
            return None
        self.ctx.lookups.put(key, detail)
        return detail


def _key(values):
    return f'report:{values["external_id"]}'


def extract_detail(text):
    """Return the dict to cache for a detail page: elevation, grade, exposure, texts.

    `{'gone': True}` for a page without a report (the PHP "Fatal error" of an
    unknown id).
    """
    soup = htmlparse.parse(text)
    if soup.select_one(TITLE) is None:
        return {'gone': True}
    found = {}
    for field, texts in LABELS.items():
        found[field] = [
            _text(soup.select_one(_value(text)))
            for text in texts
            if soup.select_one(_value(text)) is not None
        ]
    elevations = [_int(v) for v in found['elevation']]
    elevation = next((e for e in elevations if e and 300 <= e <= 4810), None)
    rating = next((v for v in found['rating'] if v), None)
    return {
        'gone': False,
        'elevation': elevation,
        'rating': rating,
        'orientations': list(orientations(found['exposure'])),
        'texts': extract_texts(labelled_values(soup)),
    }


# -- the free texts (stored by the job, never served) -------------------------


def _plain(node):
    """Return the plain text of a cell: `<br>` as new lines, no comment, no tag."""
    parts = []
    for child in node.descendants:
        if isinstance(child, Tag) and child.name in ('br', 'p', 'div', 'li'):
            parts.append('\n')
        elif isinstance(child, NavigableString) and not isinstance(child, Comment):
            parts.append(str(child))
    lines = (
        re.sub(r'[ \t\r\xa0]+', ' ', line).strip()
        for line in ''.join(parts).split('\n')
    )
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
    return fix_mojibake(text)


def labelled_values(soup):
    """Return `{label: plain value}` of the free-text rows of a detail page.

    The value is the cell after the label (`td.reportrow`, `td.reportcommento`
    for the comment). Only the rows of `TEXT_LABELS` are read: never the author
    row, whose HTML comment holds the e-mail of the author.
    """
    values = {}
    for text in TEXT_LABELS:
        for label in soup.select(_label(text)):
            cell = label.find_next_sibling('td')
            name = _text(label)
            if cell is not None and name and name not in values:
                values[name] = _plain(cell)
    return values


def _kind(label):
    for text, kind in TEXT_LABELS.items():
        if text.lower() in label.lower():
            return kind
    return None


def extract_texts(labels):
    """Map the free-text rows of a report to the kinds of texts: `{kind: text}`.

    `labels` is `{label: plain value}` (`labelled_values`). The rows of one kind
    are joined, each prefixed by its label when there are several ('Neve
    prevalente: Farinosa'); empty values, 'nessuno' and e-mail addresses are
    left out. None when there is no text.
    """
    by_kind = {}
    for label, value in labels.items():
        kind = _kind(label)
        text = _EMAIL.sub('', fix_mojibake(value or ''))
        text = '\n'.join(line.strip() for line in text.split('\n')).strip()
        if not kind or not text or text.lower() in _NOTHING:
            continue
        by_kind.setdefault(kind, []).append((label.strip(), text))
    texts = {}
    for kind, items in by_kind.items():
        if len(items) == 1 and kind == 'narrative':
            text = items[0][1]
        else:
            text = '\n'.join(f'{label}: {value}' for label, value in items)
        texts[kind] = text[:TEXT_MAX_LENGTH]
    return texts or None
