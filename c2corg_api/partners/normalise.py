"""Normalisation of what the partner sites publish (design section 6)."""

import datetime
import html as html_lib
import math
import re
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from c2corg_api.models.common.attributes import orientation_types, ski_ratings

# source -> source activity code -> (c2c activities, steep). The skitour
# activities are handled in its adapter (all skitouring, steep from the rating).
ACTIVITY_MAP: dict[str, dict[str, tuple[tuple[str, ...], bool]]] = {
    'gulliver': {
        'skimo': (('skitouring',), False),
        'skisteep': (('skitouring',), True),
        'snowshoe': (('snowshoeing',), False),
        'ciaspole': (('snowshoeing',), False),
        'hike': (('hiking',), False),
        'climb': (('rock_climbing',), False),
        # assumed codes, to confirm on the first live recording
        'alpinism': (('mountain_climbing',), False),
        'ice': (('ice_climbing',), False),
        'ferrata': (('via_ferrata',), False),
        'mtb': (('mountain_biking',), False),
    },
    # the sports of bivouak.net (bit of `data-sport`): there is no climbing,
    # alpinism or ice sport on the site
    'bivouak': {
        'ski': (('skitouring',), False),  # steep from the rating
        'rando': (('hiking',), False),  # "Rando / Trail"
        'raquettes': (('snowshoeing',), False),
        'vtt': (('mountain_biking',), False),
        'parapente': (('paragliding',), False),
    },
}

# Blachere grade -> (min, max) c2c ski ratings
BLACHERE = {'MS': ('1.1', '2.3'), 'BS': ('2.1', '3.3'), 'OS': ('4.1', '5.6')}

_BLACHERE_RE = re.compile(r'^(MS|BS|OS)A?$')
_STEEP_FROM = ski_ratings.index('4.1')
_BLOCK_TAGS = re.compile(r'</?(?:br|p|div|li|ul|ol|tr|td|h[1-6])\b[^>]*>', re.I)
_TAGS = re.compile(r'<[^>]*>')
_SPACES = re.compile(r'\s+')
_ORIENTATION_SEP = re.compile(r'[-/\s,;]+')


def map_activity(source, code):
    """Return `(activities, steep)` for a source activity code, or None."""
    if not isinstance(code, str):
        return None
    return ACTIVITY_MAP.get(source, {}).get(code.strip().lower())


def ski_rating(value):
    """Return the value as a c2c ski rating ('4.1'), or None if it is not one."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text if text in ski_ratings else None


def blachere(raw):
    """Parse a Blachere grade: `(min, max, steep)` c2c ratings, or None.

    The `A` suffix (alpine variant) is accepted, the case is ignored.
    """
    if not isinstance(raw, str):
        return None
    match = _BLACHERE_RE.match(raw.strip().upper())
    if not match:
        return None
    grade = match.group(1)
    low, high = BLACHERE[grade]
    return low, high, grade == 'OS'


def is_steep_ski(min_rating):
    """Whether a ski rating is steep skiing (4.1 and above)."""
    rating = ski_rating(min_rating)
    return rating is not None and ski_ratings.index(rating) >= _STEEP_FROM


def orientations(raw) -> tuple[str, ...]:
    """Return the orientations of 'N-NE', 'ne/e', ['S', 'SW']..., in order."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = _ORIENTATION_SEP.split(raw.strip().upper())
    elif isinstance(raw, Iterable):
        parts = [str(part).strip().upper() for part in raw]
    else:
        return ()
    result: list[str] = []
    for part in parts:
        if part in orientation_types and part not in result:
            result.append(part)
    return tuple(result)


def clean_text(html, max_len):
    """Strip tags, unescape entities, collapse spaces, truncate with '…'."""
    if html is None:
        return ''
    text = _BLOCK_TAGS.sub(' ', str(html))
    text = _TAGS.sub('', text)
    text = html_lib.unescape(text)
    text = _SPACES.sub(' ', text.replace('\xa0', ' ')).strip()
    if len(text) > max_len:
        text = text[: max(max_len - 1, 0)].rstrip() + '…'
    return text[:max_len] if max_len < 1 else text


def valid_lonlat(lon, lat) -> bool:
    """Whether the WGS 84 coordinates are usable (no NaN, range, (0, 0))."""
    for value in (lon, lat):
        if isinstance(value, bool) or not isinstance(value, int | float):
            return False
        if not math.isfinite(value):
            return False
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return False
    return not (lon == 0 and lat == 0)


def local_date(value, tz) -> datetime.date:
    """Return the local date of an epoch or a datetime in the time zone `tz`.

    Strings are accepted as the APIs send them: digits are an epoch
    ('1764000000'), anything else an ISO date or datetime ('2026-11-23',
    '2026-11-23 10:15:00', '2026-11-23T09:15:00Z'). A naive datetime is
    taken to be local already. Raises TypeError or ValueError otherwise.
    """
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if isinstance(value, str):
        text = value.strip()
        value = (
            int(text)
            if text.lstrip('-').isdigit()
            else datetime.datetime.fromisoformat(text)
        )
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(zone).date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f'not an epoch or a datetime: {value!r}')
    return datetime.datetime.fromtimestamp(value, zone).date()


def to_int(value):
    """Convert numbers and numeric strings to int; None if not numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        try:
            return int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                return None
    if isinstance(value, float):
        return round(value) if math.isfinite(value) else None
    return None
