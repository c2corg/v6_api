"""bivouak.net: the outings of the "Dernières sorties" lists (design 5-6).

One list per sport (`liste_des_sorties.php?id_sport=<bit>`, 30 cards each, the
newest first): the sports of the site are a bit mask, 1 ski, 2 hiking, 4 mountain
biking, 8 snowshoeing, 16 paragliding, and `data-sport` of a card tells which.
One list per sport, rather than the "all sports" one, so that the paragliding
reports (more than half of the "all" list in autumn) do not push the ski tours
out of it.

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
from c2corg_api.partners.adapter import ParseError
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
# the sports, in the order they are listed and looked up: bit -> code
SPORTS = {1: 'ski', 2: 'rando', 8: 'raquettes', 4: 'vtt', 16: 'parapente'}
MAX_DETAIL_FETCHES = 10  # new detail pages per run
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
    # 5 lists + MAX_DETAIL_FETCHES detail pages
    rate = RateLimit(10.0, 5 + MAX_DETAIL_FETCHES, 30)
    REQUIRED_PATHS: ClassVar[dict[str, list[str]]] = {}
    # endpoint -> every CSS selector read from it (`contract.py`): the check of
    # the live shapes, and the allow-list of what a recording keeps. The
    # excerpt of a card (`.bk-card__text`) is not in it, nor are the photos.
    REQUIRED_SELECTORS: ClassVar[dict[str, list[str]]] = {
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

    def fetch(self, ctx: FetchContext) -> FetchResult:
        result = FetchResult(outings=[], skipped=Counter())
        _Run(ctx, result).harvest()
        # nothing is remembered between runs but the lookups
        result.cursor = dict(ctx.cursor) if ctx.cursor else None
        return result


class _Run:
    def __init__(self, ctx, result):
        self.ctx = ctx
        self.result = result
        self.seen = set()
        self.detail_fetches = 0
        self.requests = LookupRequests(ctx, result)

    def harvest(self):
        by_sport = [self._list(bit) for bit in SPORTS]
        # the sports take turns for the detail pages, the newest outings first
        for turn in turns(by_sport):
            for draft in turn:
                self.result.outings.append(self._locate(draft))

    # -- the lists ---------------------------------------------------------

    def _list(self, bit):
        """Return the drafts (new outings of the period) of the list of a sport."""
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
        return HarvestedOuting(**values)

    def _detail(self, external_id, url):
        """Return the dict of a detail page, None when it cannot be had this run."""
        key = f'sortie:{external_id}'
        cached = self.ctx.lookups.get(key)
        if cached is not None:
            return cached
        if self.detail_fetches >= MAX_DETAIL_FETCHES or not self.requests.available:
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
