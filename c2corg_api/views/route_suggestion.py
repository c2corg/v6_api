"""The routes an outing's GPS track most likely followed, best first."""
# Used by the outing editor once a track is added: it lists these routes to
# associate. The score was tuned on 300 outings of a 2018 dump with a track
# and one route: the right route is in the first 5 for 89% of them (29% when
# sorted by title, as the editor did from a search in the map box).
#
# Elasticsearch only has the point of a route, so this runs in PostGIS, which
# has the route tracks and the waypoints.
#
# Production runs PostGIS 2.3: no ST_LineInterpolatePoints (2.5), hence
# ST_LineInterpolatePoint and generate_series. Measuring the route track
# inside a buffer of the outing track ranked as well but took 1 to 2 s (p90):
# with the samples, the whole query takes 6 ms (median), 12 ms (p90).
#
# With PostgreSQL 11+, JIT compiling this query costs more than running it
# (~150 ms): see #2635.

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import String

from c2corg_api.models import DBSession
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import route_documents_config

# the track is simplified to this tolerance first, in metres
SIMPLIFY = 20
# the candidates: the routes whose point is this close to the track, in metres
CANDIDATE_DISTANCE = 2000
# and only the nearest ones: a track has ~50 candidates (99% of the outing
# tracks are under 63 km). This bounds the cost of a public GET: a 150 km
# zigzag of 5000 points had 2500 candidates and took 2 s.
MAX_CANDIDATES = 300
# a waypoint or a point of a route track this close is on the track, in metres
NEAR = 300
# the points taken along a route track: SAMPLES + 1
SAMPLES = 20
# the weights of the score
TRACK_WEIGHT = 2
MAIN_WAYPOINT_WEIGHT = 1
WAYPOINTS_WEIGHT = 1
# the distance between the route point and the track lowers the score by 1
# every DISTANCE_SCALE metres
DISTANCE_SCALE = 10000
# the popularity (the outings of the route) only sorts routes that geometry
# alone cannot tell apart, as routes to the same summit: on a log scale, and
# small, so that the routes with few outings are still found
POPULARITY_WEIGHT = 0.2

LIMIT_DEFAULT = 50
LIMIT_MAX = 100

# Distances are in metres on the ground: EPSG:3857 stretches them by
# 1 / cos(latitude), so the distances in metres are multiplied by `k`.
# The candidates use the index on the route point (ST_DWithin). The overlap is
# only computed for a route track whose box touches the track.
SUGGESTION_QUERY = text(
    """
with t as (
  select st_simplify(st_transform(line, 3857), :simplify * k) trk, k
  from (
    select line, 1 / cos(radians(st_y(st_centroid(line)))) k
    from (select st_setsrid(st_geomfromtext(:wkt), 4326) line) l
  ) s
),
c as (
  select r.document_id rid, r.main_waypoint_id main_wp, g.geom rgeom,
    g.geom_detail rtrk, t.trk, t.k
  from t
  join guidebook.documents_geometries g
    on st_dwithin(g.geom, t.trk, :candidate_distance * t.k)
  join guidebook.routes r on r.document_id = g.document_id
  join guidebook.documents d
    on d.document_id = r.document_id and d.redirects_to is null
  where cast(:activities as varchar[]) is null
    or cast(r.activities as varchar[]) && cast(:activities as varchar[])
  order by st_distance(g.geom, t.trk)
  limit :max_candidates
),
s as (
  select c.rid, st_distance(c.rgeom, c.trk) / c.k distance,
    coalesce((
      select avg(st_dwithin(st_lineinterpolatepoint(p.geom, i::float / :samples),
        c.trk, :near * c.k)::int)
      from st_dump(c.rtrk) p, generate_series(0, :samples) i
      where c.rtrk && st_expand(c.trk, :near * c.k)
        and st_dimension(c.rtrk) = 1 and st_length(p.geom) > 0
    ), 0) track,
    coalesce((
      select st_dwithin(wg.geom, c.trk, :near * c.k)::int
      from guidebook.documents_geometries wg
      where wg.document_id = c.main_wp
    ), 0) main_waypoint,
    coalesce((
      select avg(st_dwithin(wg.geom, c.trk, :near * c.k)::int)
      from guidebook.associations a
      join guidebook.documents_geometries wg
        on wg.document_id = a.parent_document_id
      where a.child_document_id = c.rid and a.parent_document_type = 'w'
    ), 0) waypoints,
    (
      select count(*) from guidebook.associations a
      where a.parent_document_id = c.rid and a.child_document_type = 'o'
    ) outings
  from c
)
select rid from s
order by :track_weight * track + :main_waypoint_weight * main_waypoint
  + :waypoints_weight * waypoints - distance / :distance_scale
  + :popularity_weight * ln(1 + outings) desc, distance, rid
limit :limit
"""
).bindparams(bindparam('activities', type_=ARRAY(String)))


def suggest_routes(request):
    """Return the routes near a GPS track, the most likely first."""
    validated = request.validated
    ids = suggested_route_ids(
        validated['track'],
        validated.get('activities'),
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
    )
    # the listing keeps the order of the ids
    return get_documents_for_ids(ids, validated.get('lang'), route_documents_config)


def suggested_route_ids(points, activities, limit):
    """Return the ids of the routes near a track of (lon, lat), best first."""
    wkt = 'LINESTRING({})'.format(', '.join(f'{lon!r} {lat!r}' for lon, lat in points))
    rows = DBSession.execute(
        SUGGESTION_QUERY,
        {
            'wkt': wkt,
            'activities': activities or None,
            'limit': limit,
            'simplify': SIMPLIFY,
            'candidate_distance': CANDIDATE_DISTANCE,
            'max_candidates': MAX_CANDIDATES,
            'near': NEAR,
            'samples': SAMPLES,
            'track_weight': TRACK_WEIGHT,
            'main_waypoint_weight': MAIN_WAYPOINT_WEIGHT,
            'waypoints_weight': WAYPOINTS_WEIGHT,
            'distance_scale': DISTANCE_SCALE,
            'popularity_weight': POPULARITY_WEIGHT,
        },
    )
    return [rid for (rid,) in rows]


def decode_polyline(encoded, precision=5):
    """Return the (lon, lat) points of an encoded polyline."""
    # The encoded polyline format of Google, as ol/format/Polyline writes it:
    # each value is the difference from the previous one, times 10^precision,
    # in chunks of 5 bits (+ 63, as ASCII). It is lat, lon: points are
    # returned as lon, lat. A malformed string raises ValueError.
    values = []
    value = shift = 0
    # 6 chunks hold 30 bits: more than any longitude or latitude needs, and a
    # longer value would only grow an integer from a hostile string
    max_shift = 30
    for char in encoded:
        byte = ord(char) - 63
        if not 0 <= byte < 64:
            raise ValueError(f'invalid character {char!r}')
        if shift >= max_shift:
            raise ValueError('value too long')
        value |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            values.append(~(value >> 1) if value & 1 else value >> 1)
            value = shift = 0
    if shift or len(values) % 2:
        raise ValueError('truncated polyline')
    factor = 10**precision
    points = []
    lat = lon = 0
    for i in range(0, len(values), 2):
        lat += values[i]
        lon += values[i + 1]
        points.append((lon / factor, lat / factor))
    return points
