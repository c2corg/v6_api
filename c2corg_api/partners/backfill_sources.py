"""TEMPORARY: read the older outings of the partner sites (the backfill).

Delete with the other `backfill_*` files once the history is imported
(c2corg/v6_api#2763).

The harvest reads the latest reports of each site. A backfiller pages through
the older ones, a few pages at a time (`step`), from the newest down to a date
floor (`ctx.since`), and returns them as the adapter would: it reuses the
parsing of the adapter (its `_Run` and helpers), so a backfilled outing is the
row the harvest would have stored. The position of the walk is the cursor of
the result (`{'done': True, ...}` once the floor or the end of the site is
reached), stored by the job (`jobs/backfill_partner_outings.py`) and handed
back at the next step.

How each site lists its older reports (checked 2026-11-28):

- skitour.fr: the API takes a season (`a=2024`: Sept 2023 to Aug 2024) and up to
  1000 outings a page (`l`, `p`).
- gulliver.it: `mobile/commentglobal?page=N` pages back without an end (30
  reports a page, by outing date).
- bivouak.net: `liste_des_sorties.php?id_sport=<bit>&start=<page>`, 30 cards a
  page, back to 2003.
- gipfelbuch.ch: the listing has a "more results" button: a POST of its form
  (`/conditions/list`, a token and the cookie of the listing page, an offset)
  answering the reports as JSON with the HTML template of a row; 130 000
  reports.
- skitourenportal.eu: `/<state>?page=N`, 16 reports a page, back to 2013.
- on-ice.it: the list of all the types stops after 10 pages, the list of one
  type (`onice_reports.php?type=1&u=0&start=N`, 60 rows) goes back to the start.

A cursor made by an older version of a backfiller is not migrated: reset the
source (`--reset`).
"""

import datetime
import logging
import re
from collections import Counter
from typing import ClassVar, Protocol

from c2corg_api.partners import htmlparse
from c2corg_api.partners.adapter import ParseError, require_secrets
from c2corg_api.partners.model import FetchContext, FetchResult
from c2corg_api.partners.sources import (
    bivouak,
    gipfelbuch,
    gulliver,
    onice,
    skitour,
    skitourenportal,
)

log = logging.getLogger(__name__)


class Backfiller(Protocol):
    name: ClassVar[str]
    # the defaults of a step: pages of the listing, secondary requests
    # (detail pages, routes, summits) of new outings
    pages_per_run: ClassVar[int]
    details_per_run: ClassVar[int]

    def requests(self, pages: int, details: int) -> int:
        """Return the request budget of a step."""
        ...

    def step(self, ctx: FetchContext, pages: int, details: int) -> FetchResult: ...


def _done(cursor):
    return {**cursor, 'done': True}


def _floor_reached(kept, too_old):
    """Tell whether a page is past the floor: it had items, all too old."""
    return kept == 0 and too_old > 0


# -- skitour.fr --------------------------------------------------------------


def season_of(day):
    """Return the skitour season of a day: 2025 runs from 2024-09-01 to 2025-08-31."""
    return day.year + 1 if day.month >= 9 else day.year


class SkitourBackfill:
    """The seasons of the API, the newest first, 1000 outings a request.

    The API allows 1000 requests a day, shared with the harvest (about 100 a
    day): a season of a few thousand outings is a few requests.
    """

    name = 'skitour'
    PAGE_SIZE = 1000  # the most the API answers
    pages_per_run = 5
    details_per_run = 0

    def requests(self, pages, details):
        return pages

    def step(self, ctx, pages, details):
        adapter = skitour.SkitourAdapter()
        require_secrets(ctx, adapter.required_secrets)
        headers = {'cle': ctx.secrets['SKITOUR_API_KEY']}
        cursor = dict(ctx.cursor or {})
        season = cursor.get('season') or season_of(ctx.now.date())
        page = cursor.get('page') or 1
        result = FetchResult(outings=[], skipped=Counter())
        for _ in range(pages):
            if datetime.date(season, 8, 31) < ctx.since:
                break
            response = ctx.transport.get(
                skitour.API_URL,
                params={'c': 1, 'l': self.PAGE_SIZE, 'a': season, 'p': page},
                headers=headers,
            )
            items = adapter._items(response)
            for item in items:
                adapter._handle(item, ctx, result)
            if len(items) < self.PAGE_SIZE:
                season, page = season - 1, 1
            else:
                page += 1
        result.cursor = {'season': season, 'page': page}
        if datetime.date(season, 8, 31) < ctx.since:
            result.cursor = _done(result.cursor)
        return result


# -- gulliver.it -------------------------------------------------------------


class _GulliverRun(gulliver._Run):
    def __init__(self, ctx, result, page, pages, routes):
        super().__init__(ctx, result)
        # the floor is the floor: no look back before it
        self.floor = ctx.since
        self.max_route_fetches = routes
        self.page = page
        self.pages = pages
        self.done = False

    def _discover(self):
        # the pages only: the front page lists the latest reports
        for _ in range(self.pages):
            comments = self._page(self.page)
            if not comments:
                self.done = True
                return
            self.page += 1
            dates = [self._listed(comment) for comment in comments]
            dates = [d for d in dates if d is not None]
            if dates and max(dates) < self.ctx.since:
                self.done = True
                return


class GulliverBackfill:
    """The pages of `commentglobal`, then the routes of their reports.

    The pages are sorted by outing date: a page read again after new reports
    pushed it back is harmless (upserts), none is skipped.
    """

    name = 'gulliver'
    pages_per_run = 10
    details_per_run = 30  # routes

    def requests(self, pages, details):
        return pages + details

    def step(self, ctx, pages, details):
        cursor = dict(ctx.cursor or {})
        result = FetchResult(outings=[], skipped=Counter())
        run = _GulliverRun(ctx, result, cursor.get('page') or 1, pages, details)
        run.harvest()
        result.cursor = {'page': run.page}
        if run.done:
            result.cursor = _done(result.cursor)
        return result


# -- bivouak.net -------------------------------------------------------------

BIVOUAK_SPORTS = list(bivouak.SPORTS)  # the bits, in the order of the adapter
BIVOUAK_EMPTY = 'Aucune sortie'  # the text of a page past the end


class _BivouakRun(bivouak._Run):
    def __init__(self, ctx, result, details):
        super().__init__(ctx, result)
        self.max_detail_fetches = details

    def page(self, bit, start):
        """Return the drafts of a page of a list, and whether the list ends there."""
        response = self.ctx.transport.get(
            bivouak.LIST_URL, params={'id_sport': bit, 'start': start}
        )
        if response.status != 200:
            raise ParseError(f'liste_des_sorties {bit} {start}: HTTP {response.status}')
        soup = htmlparse.parse(response.text('utf-8'))
        cards = soup.select(bivouak.CARD)
        if not cards:
            if (
                soup.select_one('div.bk-lt') is None
                and BIVOUAK_EMPTY not in soup.get_text()
            ):
                raise ParseError(f'liste_des_sorties {bit} {start}: no list')
            return [], True
        too_old = self.result.skipped['too_old']
        drafts = []
        for card in cards:
            draft = self._card(card)
            if draft is not None:
                draft['bit'] = bit
                drafts.append(draft)
        return drafts, _floor_reached(
            len(drafts), self.result.skipped['too_old'] - too_old
        )


class BivouakBackfill:
    """The pages of the list of each sport, then the detail pages (10 s apart).

    `robots.txt` asks for 10 s between two requests: a step of 5 pages and 10
    detail pages takes 2.5 minutes. The outings over the cap of detail pages
    keep their hints (massif, summit of the title), located by the job.
    """

    name = 'bivouak'
    pages_per_run = 5
    details_per_run = 10

    def requests(self, pages, details):
        return pages + details

    def step(self, ctx, pages, details):
        cursor = dict(ctx.cursor or {})
        index = cursor.get('sport') or 0
        start = cursor.get('start') or 1
        result = FetchResult(outings=[], skipped=Counter())
        run = _BivouakRun(ctx, result, details)
        drafts = []
        for _ in range(pages):
            if index >= len(BIVOUAK_SPORTS):
                break
            page_drafts, end = run.page(BIVOUAK_SPORTS[index], start)
            drafts.extend(page_drafts)
            if end:
                index, start = index + 1, 1
            else:
                start += 1
        for draft in drafts:
            result.outings.append(run._locate(draft))
        result.cursor = {'sport': index, 'start': start}
        if index >= len(BIVOUAK_SPORTS):
            result.cursor = _done(result.cursor)
        return result


# -- gipfelbuch.ch -----------------------------------------------------------

GIPFELBUCH_LIST_URL = f'{gipfelbuch.SITE_URL}/conditions/list'
GIPFELBUCH_TOKEN = 'input#dvf_csrf_token'


def render_template(template, item):
    """Render a row of gipfelbuch as its script does (`dvf_template`).

    `{{#key}}...{{/key}}` is kept when the value is set, `{{key}}` replaced by
    the value. The site sends the values with `&` already escaped (`&amp;`),
    not the quotes: those are escaped here, so that a value never breaks an
    attribute.
    """
    out = template
    for key, value in item.items():
        if f'{{{{#{key}}}}}' in out:
            if value not in ('', 0, False):
                out = out.replace(f'{{{{#{key}}}}}', '').replace(f'{{{{/{key}}}}}', '')
            else:
                out = re.sub(
                    re.escape(f'{{{{#{key}}}}}') + '.*?' + re.escape(f'{{{{/{key}}}}}'),
                    '',
                    out,
                    flags=re.S,
                )
        text = '' if value is None else str(value)
        text = text.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        out = out.replace(f'{{{{{key}}}}}', text)
    return out


class _GipfelbuchRun(gipfelbuch._Run):
    def __init__(self, ctx, result, details):
        super().__init__(ctx, result)
        self.max_detail_fetches = details


class GipfelbuchBackfill:
    """The "more results" of the listing (POST, JSON), then the summit pages.

    One GET of the listing for the form token and its cookie, then the POSTs
    of the form, `LIMIT` reports each from the offset of the cursor. Each
    report is rendered with the template of the answer and read by the
    adapter, as a row of the listing.
    """

    name = 'gipfelbuch'
    LIMIT = 66  # as the site asks
    pages_per_run = 10
    details_per_run = 15  # summits

    def requests(self, pages, details):
        return 1 + pages + details

    def step(self, ctx, pages, details):
        cursor = dict(ctx.cursor or {})
        offset = cursor.get('offset') or 0
        result = FetchResult(outings=[], skipped=Counter())
        run = _GipfelbuchRun(ctx, result, details)
        token = self._token(ctx)
        done = False
        for _ in range(pages):
            items, template = self._page(ctx, token, offset)
            if not items:
                done = True
                break
            kept, too_old = len(result.outings), result.skipped['too_old']
            for item in items:
                markup = render_template(template, item)
                article = htmlparse.parse(markup).select_one(gipfelbuch.ARTICLE)
                if article is None:
                    result.item_errors += 1
                    log.warning(
                        'gipfelbuch backfill: row %s unreadable', item.get('id')
                    )
                    continue
                run._article(article)
            offset += self.LIMIT
            if _floor_reached(
                len(result.outings) - kept, result.skipped['too_old'] - too_old
            ):
                done = True
                break
        result.cursor = {'offset': offset}
        if done:
            result.cursor = _done(result.cursor)
        return result

    @staticmethod
    def _token(ctx):
        response = ctx.transport.get(gipfelbuch.LIST_URL)
        if response.status != 200:
            raise ParseError(f'listing: HTTP {response.status}')
        field = htmlparse.parse(response.text('utf-8')).select_one(GIPFELBUCH_TOKEN)
        if field is None or not field.get('value'):
            raise ParseError('listing: no form token')
        return field['value']

    def _page(self, ctx, token, offset):
        """Return the reports from `offset` (`[]` past the end) and the template."""
        response = ctx.transport.post(
            GIPFELBUCH_LIST_URL,
            data={
                'dvf_csrf_token': token,
                'src_conditions': '',
                'src_conditions_region': '0',
                'src_conditions_type': '0',
                'filter_conditions_limit': str(self.LIMIT),
                'filter_conditions_offset': str(offset),
                'dvForm_subm': '1',
            },
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        if response.status != 200:
            raise ParseError(f'conditions/list {offset}: HTTP {response.status}')
        try:
            data = response.json()
        except ValueError as e:
            raise ParseError(f'conditions/list {offset}: not JSON') from e
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ParseError(f'conditions/list {offset}: no items')
        # past the end: one item, a message ("Es wurden keine Einträge gefunden")
        items = [i for i in data['items'] if isinstance(i, dict) and 'id' in i]
        template = data.get('template')
        if items and not isinstance(template, str):
            raise ParseError(f'conditions/list {offset}: no template')
        return items, template


# -- skitourenportal.eu ------------------------------------------------------

SKITOURENPORTAL_STATES = list(skitourenportal.STATES)


class SkitourenportalBackfill:
    """The pages of each state, 16 reports a page, no other request."""

    name = 'skitourenportal'
    pages_per_run = 10
    details_per_run = 0

    def requests(self, pages, details):
        return pages

    def step(self, ctx, pages, details):
        adapter = skitourenportal.SkitourenportalAdapter()
        cursor = dict(ctx.cursor or {})
        index = cursor.get('state') or 0
        page = cursor.get('page') or 1
        result = FetchResult(outings=[], skipped=Counter())
        rows, markers = {}, {}
        for _ in range(pages):
            if index >= len(SKITOURENPORTAL_STATES):
                break
            kept, too_old = len(rows), result.skipped['too_old']
            _, has_next = adapter._page(
                ctx, result, rows, markers, SKITOURENPORTAL_STATES[index], page
            )
            if not has_next or _floor_reached(
                len(rows) - kept, result.skipped['too_old'] - too_old
            ):
                index, page = index + 1, 1
            else:
                page += 1
        for tour_id, row in rows.items():
            try:
                result.outings.append(
                    adapter._outing(row, markers.get(tour_id), result)
                )
            except ValueError as e:
                result.item_errors += 1
                log.warning('skitourenportal %s: %s', tour_id, e)
        result.cursor = {'state': index, 'page': page}
        if index >= len(SKITOURENPORTAL_STATES):
            result.cursor = _done(result.cursor)
        return result


# -- on-ice.it ---------------------------------------------------------------

ONICE_TYPES = list(onice.TYPES)


class _OniceRun(onice._Run):
    def __init__(self, ctx, result, details):
        super().__init__(ctx, result)
        self.max_detail_fetches = details

    def page(self, report_type, start):
        """Return the drafts of a page of the list of a type, and its rows."""
        response = self.ctx.transport.get(
            onice.LIST_URL, params={'type': report_type, 'u': 0, 'start': start}
        )
        if response.status != 200:
            raise ParseError(
                f'onice_reports {report_type} {start}: HTTP {response.status}'
            )
        soup = htmlparse.parse(onice.decode(response.body))
        columns = {
            onice._text(td).lower().rstrip('.'): i
            for i, td in enumerate(soup.select(onice.HEADER))
        }
        if not {'data', 'gita'} <= set(columns):
            raise ParseError(f'onice_reports {report_type} {start}: no list')
        rows = soup.select(onice.ROW)
        drafts = [d for d in (self._row(tr, columns) for tr in rows) if d is not None]
        return drafts, len(rows)


class OniceBackfill:
    """The list of each type, 60 rows a page, then the detail pages."""

    name = 'onice'
    pages_per_run = 5
    details_per_run = 15

    def requests(self, pages, details):
        return pages + details

    def step(self, ctx, pages, details):
        cursor = dict(ctx.cursor or {})
        index = cursor.get('type') or 0
        start = cursor.get('start') or 0
        result = FetchResult(outings=[], skipped=Counter())
        run = _OniceRun(ctx, result, details)
        drafts = []
        for _ in range(pages):
            if index >= len(ONICE_TYPES):
                break
            too_old = result.skipped['too_old']
            page_drafts, rows = run.page(ONICE_TYPES[index], start)
            drafts.extend(page_drafts)
            if rows < onice.PAGE_SIZE or _floor_reached(
                len(page_drafts), result.skipped['too_old'] - too_old
            ):
                index, start = index + 1, 0
            else:
                start += onice.PAGE_SIZE
        for draft in drafts:
            result.outings.append(run._outing(draft))
        result.cursor = {'type': index, 'start': start}
        if index >= len(ONICE_TYPES):
            result.cursor = _done(result.cursor)
        return result


BACKFILLERS: dict[str, type[Backfiller]] = {
    'skitour': SkitourBackfill,
    'gulliver': GulliverBackfill,
    'bivouak': BivouakBackfill,
    'gipfelbuch': GipfelbuchBackfill,
    'skitourenportal': SkitourenportalBackfill,
    'onice': OniceBackfill,
}
