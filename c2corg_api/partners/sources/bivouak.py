"""bivouak.net: the outings of the "Dernières sorties" lists (design 5-6).

One list per sport (`liste_des_sorties.php?id_sport=<bit>`, 30 cards each, the
newest first): the sports of the site are a bit mask, 1 ski, 2 hiking, 4 mountain
biking, 8 snowshoeing, 16 paragliding, and `data-sport` of a card tells which.
One list per sport, rather than the "all sports" one, so that the paragliding
reports (more than half of the "all" list in autumn) do not push the ski tours
out of it.

The site also has an RSS feed of its last 50 outings, all sports together
(`rss/outings/outings.rss`: link, title, author, date and one sport, but no
massif, elevation, rating or position). It is read first, as a cheap change
detector: the lists are read only for the sports of the outings new in the feed
(the cursor keeps the ids of the last feed), and those that still had outings
waiting for their detail page. All the lists are read on the first run, when
the feed fails or has nothing in common with the last one, and every
`LIST_MAX_AGE` (the feed is not rebuilt at once: it misses the latest reports).
A run with nothing new makes one request instead of five.

The lists have no coordinates: they are on the detail page of an outing
(`sortie-<id>-<slug>.html`, attributes `data-lat` and `data-lng` of the map). A
detail page is fetched at most once per outing (the answer, empty or not, is
kept in the `LookupCache` under `sortie:<id>`), and at most `MAX_DETAIL_FETCHES`
times per run, the sports taking turns, the newest outings first. The outings
over the cap keep the massif (`region`) and the summit named in their title
(`summit_name`), and are located by the job; the next runs look the rest up.

The text of the reports (excerpts, narratives, photo captions) is never read.
Everything is read through CSS selectors (`REQUIRED_SELECTORS`), never by position.
"""

import datetime
import logging
import re
from collections import Counter
from typing import ClassVar
from urllib.parse import urljoin

from c2corg_api.partners import htmlparse, normalise
from c2corg_api.partners.adapter import ParseError, SourceDown
from c2corg_api.partners.lookups import LookupRequests
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)

log = logging.getLogger(__name__)

BASE_URL = 'https://www.bivouak.net'
LIST_URL = f'{BASE_URL}/topos/liste_des_sorties.php'
FEED_URL = f'{BASE_URL}/rss/outings/outings.rss'
# the sports, in the order they are listed and looked up: bit -> code
SPORTS = {1: 'ski', 2: 'rando', 8: 'raquettes', 4: 'vtt', 16: 'parapente'}
MAX_DETAIL_FETCHES = 10  # new detail pages per run
# all the lists are read again after this long, whatever the feed says
LIST_MAX_AGE = datetime.timedelta(hours=3)
# the sport of a feed item (`<category>`, lower case) -> its bit: the first
# keyword found wins ("Ski de Rando" is ski); an unknown one reads every list
FEED_SPORTS = (
    ('ski', 1),
    ('raquette', 8),
    ('vtt', 4),
    ('parapente', 16),
    ('rando', 2),
    ('trail', 2),
)
# The "massif" of a report abroad is the country (French name). Anything else is
# a French massif: the site is French.
COUNTRIES = {
    'allemagne': 'DE',
    'andorre': 'AD',
    'autriche': 'AT',
    'bulgarie': 'BG',
    'espagne': 'ES',
    'grèce': 'GR',
    'islande': 'IS',
    'italie': 'IT',
    'maroc': 'MA',
    'macédoine du nord': 'MK',
    'norvège': 'NO',
    'pologne': 'PL',
    'roumanie': 'RO',
    'slovénie': 'SI',
    'slovaquie': 'SK',
    'suisse': 'CH',
}

_DATE = re.compile(r'(\d{2})-(\d{2})-(\d{4})')
_NUMBER = re.compile(r'^\s*(\d+)')
_SUMMIT_IN_TITLE = re.compile(r'\s\(([^()]+)\)\s*$')
_SORTIE = re.compile(r'sortie-(\d+)')

CARD = 'article.post_sortie'
ITEM = 'item'
ACTIVITIES = {
    code: normalise.ACTIVITY_MAP['bivouak'][code][0] for code in SPORTS.values()
}


def _int(text):
    """Return the leading integer of '2083 m' (None when there is none)."""
    match = _NUMBER.match(text or '')
    return int(match.group(1)) if match else None


def _country(massif):
    """Return the ISO country of a massif name ('' for none)."""
    if not massif:
        return None
    return COUNTRIES.get(massif.lower(), 'FR')


def _datetime(value):
    """Return the aware datetime of an ISO string of the cursor (None if bad)."""
    try:
        moment = datetime.datetime.fromisoformat(value)
    except TypeError, ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _float(value):
    try:
        return float(value)
    except TypeError, ValueError:
        return None


class BivouakAdapter:
    name = 'bivouak'
    site_name = 'bivouak.net'
    site_url = 'https://www.bivouak.net'
    required_secrets = ()
    # robots.txt asks the aggressive crawlers for a 10 s delay: we keep it.
    # the feed + 5 lists + MAX_DETAIL_FETCHES detail pages, at most
    rate = RateLimit(10.0, 1 + 5 + MAX_DETAIL_FETCHES, 30)
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {}
    # endpoint -> every CSS selector read from it (`contract.py`): the check of
    # the live shapes, and the allow-list of what a recording keeps. The
    # excerpt of a card (`.bk-card__text`) is not in it, nor are the photos.
    REQUIRED_SELECTORS: ClassVar[dict[str, list[str]]] = {
        # the feed: the link (id) and the sport of an item, nothing else (no
        # author, no excerpt)
        'outings_rss': [f'{ITEM} > guid', f'{ITEM} > category'],
        'liste_des_sorties': [
            f'{CARD} .bk-pill',
            f'{CARD} .bk-card__meta span',
            f'{CARD} .bk-card__title a',
            f'{CARD} .bk-kpi',
            f'{CARD} a.bk-author',
        ],
        'sortie': [
            '.bk-crumbs a[href*="massif-"]',
            '.bk-crumbs a[href*="sommet-"]',
            '.bk-viewer[data-lat][data-lng]',
        ],
    }

    # the elements holding a member's identity (name, profile link): a
    # recording replaces them by "user1", "user2"... (`htmlparse.trim`)
    PSEUDONYMISE_SELECTORS: ClassVar[dict[str, list[str]]] = {
        'liste_des_sorties': [f'{CARD} a.bk-author'],
    }
    # a recording keeps the first cards of a list and items of the feed only:
    # enough for the tests (the first turns of the detail pages)
    RECORD_LIMITS: ClassVar[dict[str, dict[str, int]]] = {
        'outings_rss': {ITEM: 10},
        'liste_des_sorties': {CARD: 3},
    }

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        _Run(ctx, result).harvest()
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
        cursor = self.ctx.cursor or {}
        feed = self._feed()
        bits = self._lists_to_read(cursor, feed)
        by_sport = {bit: self._list(bit) for bit in SPORTS if bit in bits}
        pending = set()
        # the sports take turns for the detail pages, the newest outings first
        for turn in turns(list(by_sport.values())):
            for draft in turn:
                self.result.outings.append(self._locate(draft))
                if draft['deferred']:
                    pending.add(draft['bit'])
        lists_at = cursor.get('lists_at')
        if bits == set(SPORTS):
            lists_at = self.ctx.now.isoformat()
        self.result.cursor = {
            # the ids of the last feed (the previous one when it failed)
            'feed': sorted(feed) if feed is not None else cursor.get('feed', []),
            'lists_at': lists_at,
            # the sports whose lists still have outings to look up
            'pending': sorted(pending),
        }

    # -- the feed ----------------------------------------------------------

    def _feed(self):
        """Return {outing id: sport bit or None} of the feed, None when it failed.

        The feed is a hint only: when it fails, every list is read, and a list
        that fails stops the run as before. A block (`SourceBlocked`) stops it.
        """
        try:
            response = self.ctx.transport.get(FEED_URL)
        except SourceDown as e:
            log.info('bivouak feed: %s', e)
            return None
        if response.status != 200:
            log.info('bivouak feed: HTTP %s', response.status)
            return None
        items = {}
        for item in htmlparse.parse(response.text('utf-8')).select(ITEM):
            match = _SORTIE.search(htmlparse.text_of(item.select_one('guid')))
            if match:
                category = htmlparse.text_of(item.select_one('category')).lower()
                items[int(match.group(1))] = next(
                    (bit for word, bit in FEED_SPORTS if word in category), None
                )
        return items or None

    def _lists_to_read(self, cursor, feed):
        """Return the bits of the sports whose list is read this run."""
        everything = set(SPORTS)
        known = set(cursor.get('feed') or ())
        lists_at = _datetime(cursor.get('lists_at'))
        if (
            feed is None
            # the first run, or nothing in common with the last feed: some
            # outings may have come and gone between the two
            or not known & set(feed)
            or lists_at is None
            or self.ctx.now - lists_at >= LIST_MAX_AGE
        ):
            return everything
        new = {feed[i] for i in set(feed) - known}
        if None in new:  # a sport the feed names otherwise: read them all
            return everything
        return (new | set(cursor.get('pending') or ())) & everything

    # -- the lists ---------------------------------------------------------

    def _list(self, bit):
        """Return the drafts (outings of the period) of the list of a sport."""
        response = self.ctx.transport.get(LIST_URL, params={'id_sport': bit})
        if response.status != 200:
            raise ParseError(f'liste_des_sorties sport {bit}: HTTP {response.status}')
        soup = htmlparse.parse(response.text('utf-8'))
        cards = soup.select(CARD)
        if not cards and soup.select_one('div.bk-lt') is None:
            raise ParseError(f'liste_des_sorties sport {bit}: no list in the page')
        drafts = []
        for card in cards:
            draft = self._card(card)
            if draft is not None:
                draft['bit'] = bit
                drafts.append(draft)
        return drafts

    def _card(self, card):
        external_id = None
        try:
            match = re.fullmatch(r'sortie_(\d+)', card.get('id') or '')
            if not match:
                raise ValueError('no outing id')
            external_id = match.group(1)
            if external_id in self.seen:
                self.result.skipped['duplicate'] += 1
                return None
            self.seen.add(external_id)
            sports = self._sports(card.get('data-sport'))
            if sports is None:
                return None
            meta = card.select_one('.bk-card__meta span')
            date_match = _DATE.search(htmlparse.text_of(meta))
            if date_match is None:
                raise ValueError('no date')
            day, month, year = (int(g) for g in date_match.groups())
            date = datetime.date(year, month, day)
            if date < self.ctx.since:
                self.result.skipped['too_old'] += 1
                return None
            link = card.select_one('.bk-card__title a')
            if link is None or not link.get('href'):
                raise ValueError('no title link')
            return self._draft(card, external_id, sports, date, meta, link)
        except (ValueError, TypeError, AttributeError) as e:
            self.result.item_errors += 1
            log.warning('bivouak outing %s: %s: %s', external_id, type(e).__name__, e)
            return None

    def _sports(self, mask):
        """Return the codes of the sports of a card, None when none is mapped.

        `data-sport` is a bit mask (an outing may be ski and snowshoe at once):
        the bits the site adds one day are counted, not guessed.
        """
        value = _int(mask)
        if value is None or value <= 0:
            raise ValueError(f'bad data-sport {mask!r}')
        codes = []
        for bit in (1 << i for i in range(value.bit_length())):
            if not value & bit:
                continue
            if bit in SPORTS and normalise.map_activity('bivouak', SPORTS[bit]):
                codes.append(SPORTS[bit])
            else:
                self.result.skipped[f'unmapped_activity:{bit}'] += 1
        return codes or None

    @staticmethod
    def _draft(card, external_id, sports, date, meta, link):
        activities = tuple(
            dict.fromkeys(a for code in sports for a in ACTIVITIES[code])
        )
        code = '+'.join(sports)
        steep = False
        # an outing without a title is shown as an empty link
        title = (
            normalise.clean_text(htmlparse.text_of(link), 300)
            or f'Sortie du {date:%d-%m-%Y}'
        )
        massif = normalise.clean_text(
            htmlparse.text_of(meta.select_one('a') if meta else None), 200
        )
        kpis = {
            htmlparse.text_of(k.select_one('span')): htmlparse.text_of(
                k.select_one('b')
            )
            for k in card.select('.bk-kpi')
        }
        values = {
            'source': 'bivouak',
            'external_id': external_id,
            'url': urljoin(LIST_URL, link['href']),
            'title': title,
            'date': date,
            'activities': activities,
            'lang': 'fr',
            'region': massif or None,
            'country': _country(massif),
            'source_activity': code,
            'elevation_max': _int(kpis.get('Alt. max')),
            'height_diff_up': _int(kpis.get('Dénivelé')) or None,
        }
        summit = _SUMMIT_IN_TITLE.search(title)
        if summit:  # the site appends the summit of the topo to the title
            values['summit_name'] = summit.group(1).strip()
        author = card.select_one('a.bk-author')
        if author is not None:
            values['author'] = (
                normalise.clean_text(htmlparse.text_of(author), 100) or None
            )
            if author.get('href'):
                values['author_url'] = urljoin(LIST_URL, author['href'])
        rating = kpis.get('Difficulté')
        if rating:
            values['rating_raw'] = rating[:50]
            if 'ski' in sports and normalise.ski_rating(rating):
                values.update(
                    ski_rating_min=rating,
                    ski_rating_max=rating,
                    rating_system='c2c_ski',
                )
                steep = normalise.is_steep_ski(rating)
        values['steep'] = steep
        return values

    # -- the detail pages --------------------------------------------------

    def _locate(self, values):
        """Return the outing, located when its detail page is (or can be) had."""
        detail = self._detail(values['external_id'], values['url'])
        values['deferred'] = detail is None
        if detail is None:
            self.result.skipped['location_deferred'] += 1
        else:
            if detail.get('summit'):
                values['summit_name'] = detail['summit']
            if detail.get('massif'):
                values['region'] = detail['massif']
            lat, lng = detail.get('lat'), detail.get('lng')
            if normalise.valid_lonlat(lng, lat):
                values.update(
                    lon=lng,
                    lat=lat,
                    # the map is centred on the summit of the topo, when there is
                    # one; else on what the author mapped
                    geom_quality='summit' if detail.get('summit') else 'route',
                )
        values['activities'] = tuple(values['activities'])
        fields = {k: v for k, v in values.items() if k not in ('bit', 'deferred')}
        return HarvestedOuting(**fields)

    def _detail(self, external_id, url):
        """Return the dict of a detail page, None when it cannot be had this run."""
        key = f'sortie:{external_id}'
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            return cached
        if (
            self.detail_fetches >= self.max_detail_fetches
            or not self.requests.available
        ):
            return None  # not remembered: nothing was tried
        self.detail_fetches += 1
        response = self.requests.get(url)
        if response is None:  # the site failed for it: asked again next run
            return None
        if response.status == 404:
            detail = _extract_detail(None)  # gone: never asked again
        elif response.status == 200:
            detail = _extract_detail(response.text('utf-8'))
        else:
            log.info('bivouak outing %s: HTTP %s', external_id, response.status)
            return None
        self.ctx.lookups.put(key, detail)
        return detail


def turns(lists):
    """Yield, turn by turn, the n-th item of each list (the shorter ones drop out)."""
    index = 0
    while True:
        turn = [items[index] for items in lists if index < len(items)]
        if not turn:
            return
        yield turn
        index += 1


def _extract_detail(text):
    """Return the dict to cache for a detail page: summit, massif and the map centre."""
    detail = {'lat': None, 'lng': None, 'summit': None, 'massif': None}
    if text is None:
        return detail
    soup = htmlparse.parse(text)
    summit = soup.select_one('.bk-crumbs a[href*="sommet-"]')
    massif = soup.select_one('.bk-crumbs a[href*="massif-"]')
    viewer = soup.select_one('.bk-viewer[data-lat][data-lng]')
    detail['summit'] = normalise.clean_text(htmlparse.text_of(summit), 200) or None
    detail['massif'] = normalise.clean_text(htmlparse.text_of(massif), 200) or None
    if viewer is not None:
        lat, lng = _float(viewer.get('data-lat')), _float(viewer.get('data-lng'))
        if normalise.valid_lonlat(lng, lat):
            detail['lat'], detail['lng'] = lat, lng
    return detail
