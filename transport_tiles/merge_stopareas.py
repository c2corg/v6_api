"""Adds the Navitia stop areas of the camptocamp database to the stops.

The stop areas (guidebook.stopareas) are the stops near the waypoints, imported
from Navitia. For each of them:

* an OSM stop within MAX_DISTANCE meters gets its ``navitia_id``: one point on
  the map, already linked to Navitia;
* without any OSM stop nearby, the stop area is added as a stop of its own
  (``source=navitia``), so it does not disappear from the map.

The OSM stops are streamed, only the stop areas are held in memory.

    DATABASE_URL=postgresql://... python3 merge_stopareas.py stops.geojsonl
"""

import json
import math
import os
import sys

from shapely import STRtree
from shapely.geometry import Point, box

MAX_DISTANCE = float(os.environ.get('MAX_STOPAREA_DISTANCE', '30'))
STOP_MIN_ZOOM = 12
METERS_PER_DEGREE = 111_320

QUERY = """
    SELECT navitia_id, stoparea_name, line, operator,
           ST_X(ST_Transform(geom, 4326)) AS lon,
           ST_Y(ST_Transform(geom, 4326)) AS lat
    FROM guidebook.stopareas
    WHERE geom IS NOT NULL
"""


def load_stopareas(database_url):
    import psycopg2

    with psycopg2.connect(database_url) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute(QUERY)
            return [
                {
                    'navitia_id': navitia_id,
                    'name': name,
                    'line': line,
                    'operator': operator,
                    'lon': lon,
                    'lat': lat,
                }
                for navitia_id, name, line, operator, lon, lat in cursor
            ]


def distance(lon1, lat1, lon2, lat2):
    """Distance in meters, accurate enough below a few hundred meters."""
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    dy = lat2 - lat1
    return math.hypot(dx, dy) * METERS_PER_DEGREE


def nearby(tree, stopareas, lon, lat, max_distance):
    """Indexes of the stop areas within max_distance meters of a point."""
    d_lat = max_distance / METERS_PER_DEGREE
    d_lon = d_lat / max(math.cos(math.radians(lat)), 0.01)
    candidates = tree.query(box(lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat))
    return [
        index
        for index in candidates
        if distance(lon, lat, stopareas[index]['lon'], stopareas[index]['lat'])
        <= max_distance
    ]


def stop_feature(stoparea):
    properties = {
        'name': stoparea['name'],
        'lines': stoparea['line'],
        'navitia_id': stoparea['navitia_id'],
        'source': 'navitia',
        'tippecanoe': {'minzoom': STOP_MIN_ZOOM},
    }
    if stoparea['operator']:
        properties['operator'] = stoparea['operator']
    return {
        'type': 'Feature',
        'properties': {key: value for key, value in properties.items() if value},
        'geometry': {
            'type': 'Point',
            'coordinates': [stoparea['lon'], stoparea['lat']],
        },
    }


def merge(stops, stopareas, max_distance=MAX_DISTANCE):
    """Yield the stops, then the stop areas that no stop matched."""
    tree = STRtree([Point(s['lon'], s['lat']) for s in stopareas])
    matched = set()
    for stop in stops:
        lon, lat = stop['geometry']['coordinates']
        close = nearby(tree, stopareas, lon, lat, max_distance)
        if close:
            nearest = min(
                close,
                key=lambda i: distance(
                    lon, lat, stopareas[i]['lon'], stopareas[i]['lat']
                ),
            )
            matched.update(close)
            stop['properties']['navitia_id'] = stopareas[nearest]['navitia_id']
        yield stop
    for index, stoparea in enumerate(stopareas):
        if index not in matched:
            yield stop_feature(stoparea)


def main(path, database_url):
    stopareas = load_stopareas(database_url)
    print(f'{len(stopareas)} stop areas')
    temporary = path + '.merged'
    count = 0
    with (
        open(path, encoding='utf-8') as source,
        open(temporary, 'w', encoding='utf-8') as target,
    ):
        stops = (json.loads(line) for line in source)
        for feature in merge(stops, stopareas):
            target.write(json.dumps(feature, ensure_ascii=False, separators=(',', ':')))
            target.write('\n')
            count += 1
    os.replace(temporary, path)
    print(f'{count} stops')


if __name__ == '__main__':
    main(sys.argv[1], os.environ['DATABASE_URL'])
