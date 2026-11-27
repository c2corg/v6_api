"""Read the points of a GPX file, safely, and nothing else.

A partner GPX file holds personal data: times, heart rate, cadence (in
`<extensions>`), the names and descriptions of waypoints, the author and the
device in `<metadata>`. Only the longitude, latitude and elevation of the points
of the tracks (`trk/trkseg/trkpt`) and routes (`rte/rtept`) are read; the rest
is never returned. Waypoints (`wpt`) are left out too.

The XML is parsed by defusedxml: no DTD, no entity, no external reference (an
XXE or a "billion laughs" file is refused), and the size is capped before
parsing. A line of more than MAX_POINTS points is simplified (Douglas-Peucker,
the tolerance doubled until it fits): a reduction of the display size, the
original file stays linked (`gpx_url`).
"""

import math
from dataclasses import dataclass
from io import BytesIO

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import iterparse

MAX_BYTES = 5 * 1024 * 1024
MAX_POINTS = 2000
# points read at most, before simplification (a bigger file is refused)
MAX_RAW_POINTS = 200_000
FIRST_TOLERANCE_M = 2.0
_EARTH = 6371008.8


class GpxError(ValueError):
    """The file is not a usable GPX: too big, not XML, hostile, no points."""


@dataclass(frozen=True, slots=True)
class Track:
    """The lines of a GPX: lists of (lon, lat, ele or None), WGS 84."""

    lines: tuple[tuple[tuple[float, float, float | None], ...], ...]
    point_count: int  # the points read in the file
    simplified: bool

    @property
    def kept_points(self) -> int:
        return sum(len(line) for line in self.lines)


def _local(tag):
    """'{http://www.topografix.com/GPX/1/1}trkpt' -> 'trkpt'."""
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _coordinate(value, low, high):
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    if not math.isfinite(number) or not low <= number <= high:
        return None
    return number


def _elevation(element):
    for child in element:
        if _local(child.tag) == 'ele':
            value = _coordinate((child.text or '').strip(), -500, 9000)
            return None if value is None else round(value, 1)
    return None


def parse(body: bytes) -> Track:
    """Return the lines of the tracks and routes of a GPX file.

    Raises GpxError for a file over MAX_BYTES, not XML or not GPX, with a
    DTD or entities, with too many points, or without any usable line.
    """
    if not isinstance(body, bytes | bytearray):
        raise GpxError('not bytes')
    if len(body) > MAX_BYTES:
        raise GpxError(f'too large: {len(body)} bytes')
    lines: list[list[tuple[float, float, float | None]]] = []
    current: list[tuple[float, float, float | None]] | None = None
    count = 0
    root_seen = False
    try:
        for event, element in iterparse(
            BytesIO(bytes(body)),
            events=('start', 'end'),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            name = _local(element.tag)
            if event == 'start':
                if not root_seen:
                    root_seen = True
                    if name != 'gpx':
                        raise GpxError('not a GPX file')
                if name in ('trkseg', 'rte'):
                    current = []
                continue
            if name in ('trkpt', 'rtept') and current is not None:
                lat = _coordinate(element.get('lat'), -90, 90)
                lon = _coordinate(element.get('lon'), -180, 180)
                if lat is not None and lon is not None and (lat, lon) != (0, 0):
                    count += 1
                    if count > MAX_RAW_POINTS:
                        raise GpxError('too many points')
                    current.append((round(lon, 6), round(lat, 6), _elevation(element)))
                element.clear()
            elif name in ('trkseg', 'rte'):
                if current and len(current) >= 2:
                    lines.append(current)
                current = None
                element.clear()
            elif name in ('wpt', 'metadata', 'extensions'):
                element.clear()
    except GpxError:
        raise
    except DefusedXmlException as e:
        raise GpxError(f'refused: {type(e).__name__}') from e
    except Exception as e:  # ParseError, encoding errors...
        raise GpxError(f'not XML: {type(e).__name__}') from e
    if not lines:
        raise GpxError('no line')
    return _fit(lines, count)


def _fit(lines, count) -> Track:
    if sum(len(line) for line in lines) <= MAX_POINTS:
        return Track(tuple(tuple(line) for line in lines), count, False)
    tolerance = FIRST_TOLERANCE_M
    while True:
        simplified = [_simplify(line, tolerance) for line in lines]
        if sum(len(line) for line in simplified) <= MAX_POINTS:
            return Track(tuple(tuple(line) for line in simplified), count, True)
        tolerance *= 2


def _xy(point, lat0):
    """Local metres (equirectangular around `lat0`): fine for a tolerance."""
    lon, lat, _ = point
    return (
        math.radians(lon) * _EARTH * math.cos(math.radians(lat0)),
        math.radians(lat) * _EARTH,
    )


def _simplify(line, tolerance):
    """Douglas-Peucker in local metres, iterative (no recursion limit)."""
    if len(line) <= 2:
        return list(line)
    lat0 = line[0][1]
    xy = [_xy(p, lat0) for p in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = xy[first], xy[last]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        worst, index = -1.0, None
        for i in range(first + 1, last):
            x, y = xy[i]
            if norm == 0:
                distance = math.hypot(x - x1, y - y1)
            else:
                distance = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if distance > worst:
                worst, index = distance, i
        if index is not None and worst > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(line, keep, strict=True) if k]


def wkt(track: Track) -> str:
    """Return the track as a WKT MULTILINESTRING, WGS 84, 2D (as c2c geometries)."""
    parts = [
        '(' + ', '.join(f'{lon} {lat}' for lon, lat, _ in line) + ')'
        for line in track.lines
    ]
    return f'MULTILINESTRING ({", ".join(parts)})'
