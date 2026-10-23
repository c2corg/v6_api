"""Builds the public transport lines and stops of an OpenStreetMap extract.

Reads an .osm.pbf extract (or any OSM file) and appends:

* one feature per line to a GeoJSON sequence: both directions of a line are
  merged into one geometry (by route_master, or network + ref);
* one feature per stop to another GeoJSON sequence.

    python3 build_lines.py extract.osm.pbf lines.geojsonl stops.geojsonl
"""

import calendar
import datetime
import json
import re
import sys
from array import array
from collections import defaultdict

import numpy as np
import osmium
import shapely
from shapely.geometry import LineString, Point, mapping
from shapely.ops import linemerge, unary_union

# minimum zoom at which a line of this mode shows up in the tiles
LINE_MIN_ZOOM = {
    'train': 6,
    'ferry': 8,
    'subway': 9,
    'tram': 9,
    'light_rail': 9,
    'monorail': 9,
    'funicular': 9,
    'aerialway': 9,
    'bus': 10,
    'trolleybus': 10,
}
STOP_MIN_ZOOM = 12
COORD_PRECISION = 1e-6
# node ids read per pass over the extract, see read_geometries
NODE_ID_WINDOW = 2_000_000_000

# lifecycle values (state=*, railway=*, highway=*) of something not in service
NOT_IN_SERVICE = {
    'proposed',
    'planned',
    'construction',
    'abandoned',
    'disused',
    'razed',
    'demolished',
}
# how a line says when it runs, shown as is when someone clicks on it
SCHEDULE_TAGS = ('opening_hours', 'seasonal', 'interval', 'service')
MAX_TAG_LENGTH = 200
DATE_PATTERN = re.compile(r'^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$')


def date_bounds(value):
    """First and last day covered by a (partial) OSM date such as 2019 or 2019-05."""
    match = DATE_PATTERN.match(value or '')
    if not match:
        return None
    year, month, day = (int(group) if group else None for group in match.groups())
    try:
        first = datetime.date(year, month or 1, day or 1)
        last_month = month or 12
        last_day = day or calendar.monthrange(year, last_month)[1]
        return first, datetime.date(year, last_month, last_day)
    except ValueError:
        return None


def is_in_service(tags, today):
    """False for lines (or ways) that are closed, abandoned or not built yet."""
    if tags.get('disused') == 'yes' or tags.get('abandoned') == 'yes':
        return False
    if tags.get('state') in NOT_IN_SERVICE:
        return False
    start = date_bounds(tags.get('start_date'))
    if start and start[0] > today:
        return False
    end = date_bounds(tags.get('end_date'))
    return not (end and end[1] < today)


def is_usable_way(tags, today):
    """A way of a route that is still there: not a disused railway, say."""
    if tags.get('railway') in NOT_IN_SERVICE or tags.get('highway') in NOT_IN_SERVICE:
        return False
    return is_in_service(tags, today)


def stop_role(role):
    return role.startswith('stop') or role.startswith('platform')


def read_relations(path, today):
    """Returns the route relations (by id), and the route_master of each."""
    routes = {}
    master_of = {}
    masters = {}
    relations = osmium.FileProcessor(path, osmium.osm.RELATION).with_filter(
        osmium.filter.TagFilter(('type', 'route'), ('type', 'route_master'))
    )
    for relation in relations:
        tags = relation.tags
        if tags.get('type') == 'route_master':
            masters[relation.id] = dict(tags)
            for member in relation.members:
                if member.type == 'r':
                    master_of[member.ref] = relation.id
        elif tags.get('route') in LINE_MIN_ZOOM and is_in_service(tags, today):
            members = [(m.type, m.ref, m.role) for m in relation.members]
            routes[relation.id] = {'tags': dict(tags), 'members': members}
    return routes, master_of, masters


def read_geometries(path, routes, today):
    """Coordinates of the member ways, position and name of the member nodes.

    Works on the whole extract with little memory: the objects are selected by
    id on the libosmium side, so Python only sees the ones the routes use, and
    the node coordinates are kept in compact arrays instead of a location index.
    """
    way_ids = set()
    node_ids = set()
    stop_way_ids = set()
    for route in routes.values():
        for member_type, ref, role in route['members']:
            if member_type == 'w':
                way_ids.add(ref)
                if stop_role(role):
                    stop_way_ids.add(ref)
            elif member_type == 'n':
                node_ids.add(ref)

    # pass 1: the nodes of the member ways
    way_refs = {}
    way_names = {}
    all_refs = array('q')
    ways_in_file = osmium.FileProcessor(path, osmium.osm.WAY).with_filter(
        osmium.filter.IdFilter(way_ids)
    )
    for way in ways_in_file:
        if not is_usable_way(way.tags, today):
            continue
        refs = array('q', (node.ref for node in way.nodes))
        way_refs[way.id] = refs
        all_refs.extend(refs)
        if way.id in stop_way_ids and way.tags.get('name'):
            way_names[way.id] = way.tags['name']
    wanted = np.unique(
        np.concatenate(
            (
                np.frombuffer(all_refs, dtype=np.int64),
                np.fromiter(node_ids, dtype=np.int64, count=len(node_ids)),
            )
        )
    )
    del all_refs

    # pass 2: their positions, in the order of the (sorted) ids
    lons = np.full(len(wanted), np.nan)
    lats = np.full(len(wanted), np.nan)
    node_names = {}
    # IdFilter keeps its ids in a bitmap with one 512 kB chunk per 4 million ids,
    # so ids scattered over the whole range (up to 13 billion) take over 1 GB.
    # One pass per window of ids keeps the number of chunks, and the memory, low.
    for start in range(0, int(wanted[-1]) + 1, NODE_ID_WINDOW):
        low = np.searchsorted(wanted, start)
        high = np.searchsorted(wanted, start + NODE_ID_WINDOW)
        if low == high:
            continue
        # a numpy array would make IdFilter use far more memory than a list
        window = osmium.filter.IdFilter(wanted[low:high].tolist())
        for node in osmium.FileProcessor(path, osmium.osm.NODE).with_filter(window):
            index = np.searchsorted(wanted, node.id)
            lons[index] = node.lon
            lats[index] = node.lat
            if node.id in node_ids and node.tags.get('name'):
                node_names[node.id] = node.tags['name']

    ways = {}
    for way_id, refs in way_refs.items():
        index = np.searchsorted(wanted, np.frombuffer(refs, dtype=np.int64))
        coords = np.column_stack((lons[index], lats[index]))
        ways[way_id] = (coords[~np.isnan(coords[:, 0])], way_names.get(way_id))
    nodes = {}
    for node_id in node_ids:
        index = np.searchsorted(wanted, node_id)
        if not np.isnan(lons[index]):
            nodes[node_id] = (
                (float(lons[index]), float(lats[index])),
                node_names.get(node_id),
            )
    return ways, nodes


def way_coords(ways, ref):
    return ways.get(ref, ([], None))[0]


def route_stops(route, ways, nodes):
    """Stops of a route: its platforms, or its stop positions without any."""
    found = {'platform': [], 'stop': []}
    for member_type, ref, role in route['members']:
        if not stop_role(role):
            continue
        kind = 'platform' if role.startswith('platform') else 'stop'
        if member_type == 'n' and ref in nodes:
            position, name = nodes[ref]
            stop_id = ref
        elif member_type == 'w' and len(way_coords(ways, ref)) >= 2:
            coords, name = ways[ref]
            centroid = LineString(coords).centroid
            position = (centroid.x, centroid.y)
            stop_id = -ref
        else:
            continue
        if name:
            found[kind].append((stop_id, position, name))
    return found['platform'] or found['stop']


def line_group(route_id, route, master_of):
    """Routes of the same group are drawn as a single line."""
    master_id = master_of.get(route_id)
    if master_id is not None:
        return ('master', master_id)
    tags = route['tags']
    return (
        'route',
        tags['route'],
        tags.get('network'),
        tags.get('ref') or tags.get('name') or route_id,
    )


def build(path, today=None):
    today = today or datetime.date.today()
    routes, master_of, masters = read_relations(path, today)
    ways, nodes = read_geometries(path, routes, today)

    groups = defaultdict(list)
    for route_id in sorted(routes):
        groups[line_group(route_id, routes[route_id], master_of)].append(route_id)

    lines = []
    stops = {}
    for key, route_ids in groups.items():
        parts = []
        for route_id in route_ids:
            for member_type, ref, role in routes[route_id]['members']:
                if (
                    member_type == 'w'
                    and not stop_role(role)
                    and len(way_coords(ways, ref)) >= 2
                ):
                    parts.append(LineString(way_coords(ways, ref)))
        if not parts:
            continue
        geometry = unary_union(parts)
        if geometry.geom_type != 'LineString':
            geometry = linemerge(geometry)
        geometry = shapely.set_precision(geometry, COORD_PRECISION)
        if geometry.is_empty:
            continue

        first = routes[route_ids[0]]['tags']
        master = masters.get(key[1], {}) if key[0] == 'master' else {}

        def tag(name):
            return first.get(name) or master.get(name)

        mode = first['route']
        properties = {
            'fid': route_ids[0],
            'rels': ','.join(str(i) for i in route_ids),
            'mode': mode,
            'ref': tag('ref'),
            'name': tag('name'),
            'network': tag('network'),
            'operator': tag('operator'),
            'colour': tag('colour'),
            'website': tag('website') or tag('contact:website') or tag('url'),
            'from': first.get('from'),
            'to': first.get('to'),
            'tippecanoe': {'minzoom': LINE_MIN_ZOOM[mode]},
        }
        for name in SCHEDULE_TAGS:
            if tag(name):
                properties[name] = tag(name)[:MAX_TAG_LENGTH]
        lines.append(
            {
                'type': 'Feature',
                'properties': {k: v for k, v in properties.items() if v},
                'geometry': mapping(geometry),
            }
        )

        label = tag('ref') or tag('name')
        for route_id in route_ids:
            for stop_id, position, name in route_stops(routes[route_id], ways, nodes):
                stop = stops.setdefault(
                    stop_id,
                    {
                        'position': position,
                        'name': name,
                        'lines': set(),
                        'modes': set(),
                    },
                )
                if label:
                    stop['lines'].add(label)
                stop['modes'].add(mode)

    stop_features = [
        {
            'type': 'Feature',
            'properties': {
                'name': stop['name'],
                'lines': ','.join(sorted(stop['lines'])),
                'modes': ','.join(sorted(stop['modes'])),
                'tippecanoe': {'minzoom': STOP_MIN_ZOOM},
            },
            'geometry': mapping(Point(*stop['position'])),
        }
        for stop in stops.values()
    ]
    return lines, stop_features


def main(path, lines_path, stops_path):
    lines, stops = build(path)
    for target, features in ((lines_path, lines), (stops_path, stops)):
        with open(target, 'a', encoding='utf-8') as out:
            for feature in features:
                out.write(
                    json.dumps(feature, ensure_ascii=False, separators=(',', ':'))
                    + '\n'
                )
    print('%d lines, %d stops' % (len(lines), len(stops)))


if __name__ == '__main__':
    main(*sys.argv[1:4])
