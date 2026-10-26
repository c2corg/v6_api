"""Joins what the extracts of two regions each know about the same line or stop.

An extract only holds what is inside its region: a line that crosses the border
is cut at the border in each of them, and the stops at the border are in both.
The OpenStreetMap ids of the relations are kept, so the pieces of one line are
the lines that share a relation. They are merged into one, and the stops
that are at the same place with the same name into one.

    python3 reconcile.py lines.geojsonl stops.geojsonl
"""

import json
import os
import sys

import shapely
from shapely.geometry import mapping, shape
from shapely.ops import linemerge, unary_union

COORD_PRECISION = 1e-6
# 5 decimals of a degree: about a meter
STOP_DECIMALS = 5


def read(path):
    with open(path, encoding='utf-8') as source:
        for line in source:
            yield json.loads(line)


def write(path, features):
    with open(path, 'w', encoding='utf-8') as target:
        for feature in features:
            target.write(json.dumps(feature, ensure_ascii=False, separators=(',', ':')))
            target.write('\n')


def relations(feature):
    return [r for r in feature['properties'].get('rels', '').split(',') if r]


class Groups:
    """Union-find: items that share a key end up in the same group."""

    def __init__(self):
        self.parent = []
        self.first = {}

    def add(self, keys):
        index = len(self.parent)
        self.parent.append(index)
        for key in keys:
            if key in self.first:
                self.union(index, self.first[key])
            else:
                self.first[key] = index
        return index

    def find(self, index):
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left, right):
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def merge_lines(pieces):
    """One line from the pieces of a line that are in different extracts."""
    pieces = sorted(pieces, key=lambda piece: piece['properties']['fid'])
    properties = {}
    for piece in pieces:
        for key, value in piece['properties'].items():
            properties.setdefault(key, value)
    properties['rels'] = ','.join(
        sorted({r for piece in pieces for r in relations(piece)}, key=int)
    )
    geometry = unary_union([shape(piece['geometry']) for piece in pieces])
    if geometry.geom_type != 'LineString':
        geometry = linemerge(geometry)
    geometry = shapely.set_precision(geometry, COORD_PRECISION)
    return {'type': 'Feature', 'properties': properties, 'geometry': mapping(geometry)}


def reconcile_lines(source, target):
    """Write the lines of `source` to `target`, the pieces of a line made one.

    Only the lines that have to be merged are kept in memory.
    """
    groups = Groups()
    for feature in read(source):
        groups.add(relations(feature))
    sizes = {}
    for index in range(len(groups.parent)):
        root = groups.find(index)
        sizes[root] = sizes.get(root, 0) + 1

    pending = {}

    def features():
        for index, feature in enumerate(read(source)):
            root = groups.find(index)
            if sizes[root] == 1:
                yield feature
            else:
                pending.setdefault(root, []).append(feature)
        for root in sorted(pending):
            yield merge_lines(pending[root])

    write(target, features())
    return sum(1 for size in sizes.values() if size > 1)


def stop_key(feature):
    lon, lat = feature['geometry']['coordinates']
    return (
        feature['properties'].get('name'),
        round(lon, STOP_DECIMALS),
        round(lat, STOP_DECIMALS),
    )


def merge_stops(stops):
    """One stop from the same stop found in several extracts."""
    first = stops[0]
    properties = dict(first['properties'])
    for stop in stops[1:]:
        for key in ('lines', 'modes'):
            values = set(properties.get(key, '').split(',')) | set(
                stop['properties'].get(key, '').split(',')
            )
            properties[key] = ','.join(sorted(value for value in values if value))
        for key, value in stop['properties'].items():
            properties.setdefault(key, value)
    return {
        'type': 'Feature',
        'properties': properties,
        'geometry': first['geometry'],
    }


def reconcile_stops(source, target):
    seen = {}
    repeated = set()
    for feature in read(source):
        key = stop_key(feature)
        if key in seen:
            repeated.add(key)
        seen[key] = True
    del seen

    pending = {}

    def features():
        for feature in read(source):
            key = stop_key(feature)
            if key in repeated:
                pending.setdefault(key, []).append(feature)
            else:
                yield feature
        for key in sorted(pending, key=str):
            yield merge_stops(pending[key])

    write(target, features())
    return len(repeated)


def main(lines_path, stops_path):
    for path, reconcile in (
        (lines_path, reconcile_lines),
        (stops_path, reconcile_stops),
    ):
        temporary = path + '.reconciled'
        merged = reconcile(path, temporary)
        os.replace(temporary, path)
        print(f'{os.path.basename(path)}: {merged} merged')


if __name__ == '__main__':
    main(*sys.argv[1:3])
