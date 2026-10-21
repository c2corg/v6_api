"""
Reads a GTFS archive and builds what the maps need: the lines (merged and
simplified paths, directions, timetables) and the stops (timetables).

This module does not use the database: see `c2corg_api.transport.importer`.
"""
import csv
import io
import math
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, transform, unary_union

from c2corg_api.transport.settings import env_float, env_int

# The thresholds are read from the environment (see `.env`), the values here
# are the defaults.

# timetables cover this number of days, from the day of the import
SERVICE_DAYS = env_int('TRANSPORT_SERVICE_DAYS', 365, minimum=1, maximum=800)

# the paths follow the roads, at most this far (in meters)
SIMPLIFY_TOLERANCE = env_float('TRANSPORT_SIMPLIFY_TOLERANCE', 5, minimum=0)

# the stop sequences of a direction that are not a part of a more frequent
# one (variants): only the most frequent are kept
MAX_VARIANTS_PER_DIRECTION = env_int(
    'TRANSPORT_MAX_VARIANTS_PER_DIRECTION', 6, minimum=1)

_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True).transform

_MODES = {
    0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
    5: 'cable_car', 6: 'cable_car', 7: 'funicular', 11: 'trolleybus',
    12: 'monorail',
}


def route_mode(route_type):
    """Maps a GTFS route type (basic or extended) to a mode."""
    try:
        route_type = int(route_type)
    except (TypeError, ValueError):
        return 'bus'
    if route_type in _MODES:
        return _MODES[route_type]
    # extended route types
    family = route_type // 100
    return {
        1: 'train', 2: 'bus', 4: 'metro', 7: 'bus', 8: 'trolleybus',
        9: 'tram', 10: 'ferry', 12: 'ferry', 13: 'cable_car',
        14: 'funicular',
    }.get(family, 'bus')


def _rows(archive, name):
    """Yields the rows of a file of the archive (nothing if it is absent)."""
    if name not in archive.namelist():
        return
    with archive.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding='utf-8-sig'))


def _minutes(value):
    """'08:05:00' -> 485 (hours can be over 24); None if empty."""
    if not value:
        return None
    try:
        hours, minutes = value.strip().split(':')[:2]
        return int(hours) * 60 + int(minutes)
    except ValueError:
        return None


def _color(value):
    value = (value or '').strip().lstrip('#').upper()
    return value if len(value) == 6 else None


def service_masks(archive, start):
    """
    Returns, for each service, the days it runs as an integer whose bit i is
    set if the service runs the day `start + i`.
    """
    days = [start + timedelta(days=i) for i in range(SERVICE_DAYS)]
    index = {day.strftime('%Y%m%d'): i for i, day in enumerate(days)}
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                'saturday', 'sunday']
    masks = defaultdict(int)

    for row in _rows(archive, 'calendar.txt'):
        first = max(row['start_date'], days[0].strftime('%Y%m%d'))
        last = min(row['end_date'], days[-1].strftime('%Y%m%d'))
        mask = 0
        for key, i in index.items():
            weekday = weekdays[days[i].weekday()]
            if first <= key <= last and row[weekday] == '1':
                mask |= 1 << i
        masks[row['service_id']] |= mask

    for row in _rows(archive, 'calendar_dates.txt'):
        i = index.get(row['date'])
        if i is None:
            continue
        if row['exception_type'] == '1':
            masks[row['service_id']] |= 1 << i
        elif row['exception_type'] == '2':
            masks[row['service_id']] &= ~(1 << i)

    return masks


class _Services:
    """Gives short keys to the service masks of one line or stop."""

    def __init__(self):
        self.keys = {}

    def key(self, mask):
        if mask not in self.keys:
            self.keys[mask] = 's%d' % len(self.keys)
        return self.keys[mask]

    def as_dict(self):
        # hexadecimal: bit i is the day `start + i`
        return {key: '%x' % mask for mask, key in self.keys.items()}


def _is_subsequence(sub, sequence):
    it = iter(sequence)
    return all(stop in it for stop in sub)


def _align(times_by_stop, pattern, main):
    """Puts the times of a trip on the columns of the pattern it is part of."""
    times = [None] * len(main)
    position = 0
    for stop_id, minutes in zip(pattern, times_by_stop):
        while main[position] != stop_id:
            position += 1
        times[position] = minutes
        position += 1
    return times


def _directions(trips, stops, services):
    """
    The directions of a line: stops in order and timetable of the trips.
    The trips that serve only a part of the stops of the most frequent
    sequence are shown in its columns.
    """
    by_direction = defaultdict(list)
    for trip in trips:
        by_direction[trip['direction_id']].append(trip)

    directions = []
    for direction_id in sorted(by_direction):
        direction_trips = by_direction[direction_id]
        frequency = Counter(tuple(t['stops']) for t in direction_trips)
        mains = []
        for pattern, _ in frequency.most_common():
            if not any(_is_subsequence(pattern, main) for main in mains):
                mains.append(pattern)
        mains = mains[:MAX_VARIANTS_PER_DIRECTION]

        for main in mains:
            # each trip belongs to the first main sequence containing it
            # (trips of the variants that were dropped are not shown)
            members = [
                t for t in direction_trips
                if next((m for m in mains
                         if _is_subsequence(t['stops'], m)), None) == main
            ]
            if not members:
                continue
            headsigns = Counter(
                t['headsign'] for t in members if t['headsign'])
            first, last = stops[main[0]]['name'], stops[main[-1]]['name']
            members.sort(key=lambda t: next(
                (m for m in t['times'] if m is not None), 0))
            directions.append({
                'direction_id': direction_id,
                'label': '%s → %s' % (first, last),
                'headsign': (headsigns.most_common(1)[0][0]
                             if headsigns else None),
                'origin': first,
                'destination': last,
                'stops': [
                    {
                        'stop_id': stop_id,
                        'name': stops[stop_id]['name'],
                        'lon': round(stops[stop_id]['lon'], 5),
                        'lat': round(stops[stop_id]['lat'], 5),
                    }
                    for stop_id in main
                ],
                'trips': [
                    {
                        'service': services.key(t['mask']),
                        'times': _align(t['times'], t['stops'], main),
                    }
                    for t in members
                ],
            })
    return directions


def _line_geometry(shapes):
    """
    Merges the shapes of a line (the two ways follow the same roads) and
    simplifies the result, in EPSG:3857 (MultiLineString), None if empty.
    """
    lines = [
        transform(_to_3857, LineString(points))
        for points in shapes if len(points) >= 2
    ]
    if not lines:
        return None
    merged = unary_union(lines)
    if merged.geom_type != 'LineString':
        merged = linemerge(merged)
    # the length of a meter depends on the latitude in EPSG:3857
    latitude = math.radians(
        sum(point[1] for pts in shapes for point in pts[:1]) / len(shapes))
    simplified = merged.simplify(
        SIMPLIFY_TOLERANCE / math.cos(latitude), preserve_topology=True)
    if simplified.geom_type == 'LineString':
        simplified = MultiLineString([simplified])
    return simplified


def parse(archive_file, today=None):
    """
    Reads a GTFS archive (path or file object) and returns
    `{'lines': [...], 'stops': [...]}`: dictionaries with what the tables
    `transport_lines` and `transport_stops` store (geometries are shapely
    objects in EPSG:3857).
    """
    today = today or date.today()
    start = today.isoformat()

    with zipfile.ZipFile(archive_file) as archive:
        masks = service_masks(archive, today)

        routes = {
            r['route_id']: r for r in _rows(archive, 'routes.txt')}
        agencies = {
            a.get('agency_id', ''): a.get('agency_name', '')
            for a in _rows(archive, 'agency.txt')}

        stops = {}
        for row in _rows(archive, 'stops.txt'):
            try:
                stops[row['stop_id']] = {
                    'id': row['stop_id'],
                    'name': row['stop_name'],
                    'lat': float(row['stop_lat']),
                    'lon': float(row['stop_lon']),
                    'parent': row.get('parent_station') or None,
                    'code': row.get('stop_code') or None,
                    'location_type': row.get('location_type') or '0',
                }
            except (KeyError, ValueError):
                continue  # no coordinates: cannot be drawn

        def station(stop_id):
            """A platform is shown with its station."""
            stop = stops[stop_id]
            parent = stop['parent']
            return parent if parent in stops else stop_id

        trips = {}
        for row in _rows(archive, 'trips.txt'):
            if row['route_id'] in routes and masks.get(row['service_id']):
                trips[row['trip_id']] = {
                    'route_id': row['route_id'],
                    'mask': masks[row['service_id']],
                    'direction_id': row.get('direction_id') or '0',
                    'headsign': (row.get('trip_headsign') or '').strip(),
                    'shape_id': row.get('shape_id') or None,
                    'stops': [],
                    'times': [],
                }

        sequences = defaultdict(list)
        for row in _rows(archive, 'stop_times.txt'):
            if row['trip_id'] in trips and row['stop_id'] in stops:
                minutes = _minutes(
                    row.get('departure_time') or row.get('arrival_time'))
                # the id of the stop is the string of stops.txt, not a copy
                # for each of the millions of rows of a large feed
                sequences[row['trip_id']].append((
                    int(row['stop_sequence']), stops[row['stop_id']]['id'],
                    minutes))
        for trip_id, sequence in sequences.items():
            sequence.sort()
            trip = trips[trip_id]
            trip['stops'] = [station(stop_id) for _, stop_id, _ in sequence]
            trip['times'] = [minutes for _, _, minutes in sequence]
        trips = {k: t for k, t in trips.items() if len(t['stops']) >= 2}

        used_shapes = {t['shape_id'] for t in trips.values() if t['shape_id']}
        shape_points = defaultdict(list)
        for row in _rows(archive, 'shapes.txt'):
            if row['shape_id'] in used_shapes:
                shape_points[row['shape_id']].append((
                    int(row['shape_pt_sequence']),
                    float(row['shape_pt_lon']),
                    float(row['shape_pt_lat'])))

    # lines
    trips_by_route = defaultdict(list)
    for trip in trips.values():
        trips_by_route[trip['route_id']].append(trip)

    lines = []
    for route_id, route_trips in trips_by_route.items():
        route = routes[route_id]
        services = _Services()
        directions = _directions(route_trips, stops, services)
        shapes = [
            [(lon, lat) for _, lon, lat in sorted(shape_points[shape_id])]
            for shape_id in sorted({
                t['shape_id'] for t in route_trips
                if t['shape_id'] in shape_points})
        ]
        short_name = (route.get('route_short_name')
                      or route.get('route_long_name') or route_id).strip()
        lines.append({
            'route_id': route_id,
            'short_name': short_name,
            'long_name': (route.get('route_long_name') or short_name).strip(),
            'mode': route_mode(route.get('route_type')),
            'color': _color(route.get('route_color')),
            'text_color': _color(route.get('route_text_color')),
            'operator': agencies.get(route.get('agency_id', '')) or None,
            'url': (route.get('route_url') or '').strip() or None,
            'geom': _line_geometry(shapes),
            'details': {
                'start': start,
                'services': services.as_dict(),
                'directions': directions,
            },
        })

    # stops: departures of the lines serving them
    line_by_route = {line['route_id']: line for line in lines}
    per_stop = defaultdict(lambda: defaultdict(list))
    ref_ids = defaultdict(set)
    for stop in stops.values():
        ref_ids[station(stop['id'])].update(
            x for x in (stop['id'], stop['code']) if x)
    for trip in trips.values():
        # the last stop is an arrival, not a departure
        for stop_id, minutes in zip(trip['stops'][:-1], trip['times'][:-1]):
            if minutes is not None:
                per_stop[stop_id][trip['route_id']].append(
                    (minutes, trip['mask'], trip['headsign']))

    stop_rows = []
    for stop_id, by_route in per_stop.items():
        stop = stops[stop_id]
        services = _Services()
        stop_lines = []
        for route_id, departures in sorted(by_route.items()):
            line = line_by_route[route_id]
            headsigns = sorted({h for _, _, h in departures})
            departures.sort(key=lambda d: d[0])
            stop_lines.append({
                'route_id': route_id,
                'short_name': line['short_name'],
                'mode': line['mode'],
                'color': line['color'],
                'text_color': line['text_color'],
                'headsigns': headsigns,
                'departures': [
                    [minutes, services.key(mask), headsigns.index(headsign)]
                    for minutes, mask, headsign in departures
                ],
            })
        modes = Counter(line['mode'] for line in stop_lines)
        stop_rows.append({
            'stop_id': stop_id,
            'name': stop['name'],
            'mode': modes.most_common(1)[0][0],
            'geom': transform(_to_3857, Point(stop['lon'], stop['lat'])),
            'ref_ids': sorted(ref_ids[stop_id] | {stop_id}),
            'details': {
                'start': start,
                'services': services.as_dict(),
                'lines': stop_lines,
            },
        })

    return {'lines': lines, 'stops': stop_rows}
