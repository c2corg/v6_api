"""
The same stop or the same line is often described by several feeds (a
regional express coach and the network of a department, a train and a regional
feed...), with other ids and other names: the stops are grouped in clusters
and the duplicate lines are hidden.

- stops: a stop is the anchor of a cluster (`cluster_id` = its own id), the
  stops around it are the other members. Around an anchor (the stop with the
  most departures, never from one stop to the next, so that a cluster does
  not follow a street), a stop is a member if it is
  - at less than SAME_PLACE_DISTANCE: whatever its name,
  - at less than NEAR_DISTANCE and its name looks like the one of the anchor,
    or one of its lines (code) also serves the anchor.
- lines: two lines of two feeds with the same mode and the same code, whose
  paths cover each other (both ways: a short line in a long one is not
  a duplicate) are duplicates; the one with the most trips is kept, the others
  are hidden (`duplicate_of`), and not deleted.

To compute them again after the imports: `transport_postprocess <config_uri>`.
"""
import logging
import re
import unicodedata
from collections import defaultdict

from sqlalchemy import text

log = logging.getLogger(__name__)

# meters: two stops this close are the same place, whatever their names
SAME_PLACE_DISTANCE = 15
# meters: two stops this close are the same place if they look like it
NEAR_DISTANCE = 50

# meters: the path of a line is covered by the one of a duplicate within this
LINE_TOLERANCE = 25
# at least this share of each path must be covered by the other
LINE_OVERLAP = 0.9

_STOP_WORDS = {
    'a', 'au', 'aux', 'd', 'de', 'des', 'du', 'en', 'et', 'l', 'la', 'le',
    'les', 'sur', 'sous', 'the', 'der', 'die', 'das', 'di', 'del', 'della',
    'arret', 'stop', 'bus',
}


def name_tokens(name):
    """
    The words of the name of a stop, without accents, case, punctuation and
    little words: "Annecy, Gare Routière" -> {annecy, gare, routiere}
    """
    name = unicodedata.normalize('NFKD', name or '')
    name = ''.join(c for c in name if not unicodedata.combining(c)).lower()
    return {
        word for word in re.split(r'[^a-z0-9]+', name)
        if word and word not in _STOP_WORDS
    }


def names_similar(a, b):
    """
    Do two names look like the same place? One contains the other ("Gare
    Routière" in "Annecy Gare Routière"), or half of their words are the same.
    """
    tokens_a, tokens_b = name_tokens(a), name_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    if tokens_a <= tokens_b or tokens_b <= tokens_a:
        return True
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b) >= 0.5


def _same_place(anchor, stop, distance):
    if distance <= SAME_PLACE_DISTANCE:
        return True
    if distance <= NEAR_DISTANCE:
        return names_similar(anchor['name'], stop['name']) \
            or bool(anchor['codes'] & stop['codes'])
    return False


def cluster_stops(stops, pairs):
    """
    Groups the stops of the same place.

    `stops`: {stop_pk: {'name', 'codes' (set of lowercase codes of the lines),
    'departures' (number)}}. `pairs`: (stop_pk, stop_pk, meters) for the stops
    closer than NEAR_DISTANCE.

    Returns {stop_pk: cluster_id}, the cluster id is the one of its anchor.
    """
    near = defaultdict(list)
    for a, b, distance in pairs:
        near[a].append((distance, b))
        near[b].append((distance, a))

    clusters = {}
    order = sorted(stops, key=lambda pk: (-stops[pk]['departures'], pk))
    for anchor in order:
        if anchor in clusters:
            continue
        clusters[anchor] = anchor
        for distance, pk in sorted(near[anchor]):
            if pk not in clusters \
                    and _same_place(stops[anchor], stops[pk], distance):
                clusters[pk] = anchor
    return clusters


def duplicate_lines(lines, pairs):
    """
    Finds the lines to hide.

    `lines`: {line_id: {'trips' (number), 'length' (meters)}}. `pairs`:
    (line_id, line_id, share of the first one covered by the second one, share
    of the second one covered by the first one) for the lines of the same mode
    and code of two feeds with paths that touch.

    Returns {hidden line id: kept line id}.
    """
    # lines of the same group (a duplicate of a duplicate is a duplicate)
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, a_in_b, b_in_a in pairs:
        if a_in_b >= LINE_OVERLAP and b_in_a >= LINE_OVERLAP:
            parent[find(a)] = find(b)

    groups = defaultdict(list)
    for line_id in parent:
        groups[find(line_id)].append(line_id)

    hidden = {}
    for group in groups.values():
        kept = min(
            group,
            key=lambda i: (-lines[i]['trips'], -lines[i]['length'], i))
        for line_id in group:
            if line_id != kept:
                hidden[line_id] = kept
    return hidden


# database

_STOPS = text("""
    SELECT stop_pk, name,
           coalesce((
               SELECT array_agg(DISTINCT lower(trim(l->>'short_name')))
               FROM jsonb_array_elements(details->'lines') l
           ), '{}') AS codes,
           coalesce((
               SELECT sum(jsonb_array_length(l->'departures'))
               FROM jsonb_array_elements(details->'lines') l
           ), 0) AS departures
    FROM guidebook.transport_stops
""")

# the distance in meters: the meter of EPSG:3857 is longer far from the equator
_STOP_PAIRS = text("""
    SELECT a.stop_pk, b.stop_pk,
           ST_Distance(a.geom, b.geom)
               * cos(radians(ST_Y(ST_Transform(a.geom, 4326)))) AS meters
    FROM guidebook.transport_stops a
    JOIN guidebook.transport_stops b ON a.stop_pk < b.stop_pk
     AND ST_DWithin(
         a.geom, b.geom,
         :distance / cos(radians(ST_Y(ST_Transform(a.geom, 4326)))))
""")

_LINES = text("""
    SELECT line_id,
           coalesce((
               SELECT sum(jsonb_array_length(d->'trips'))
               FROM jsonb_array_elements(details->'directions') d
           ), 0) AS trips,
           ST_Length(geom)
               * cos(radians(ST_Y(ST_Transform(ST_Centroid(geom), 4326))))
               AS meters
    FROM guidebook.transport_lines
    WHERE geom IS NOT NULL
""")

_LINE_PAIRS = text("""
    SELECT a.line_id, b.line_id,
        ST_Length(ST_Intersection(
            a.geom, ST_Buffer(b.geom, :tolerance / cos(radians(
                ST_Y(ST_Transform(ST_Centroid(a.geom), 4326)))))))
            / nullif(ST_Length(a.geom), 0) AS a_in_b,
        ST_Length(ST_Intersection(
            b.geom, ST_Buffer(a.geom, :tolerance / cos(radians(
                ST_Y(ST_Transform(ST_Centroid(a.geom), 4326)))))))
            / nullif(ST_Length(b.geom), 0) AS b_in_a
    FROM guidebook.transport_lines a
    JOIN guidebook.transport_lines b ON a.line_id < b.line_id
     AND a.feed_id <> b.feed_id
     AND a.mode = b.mode
     AND lower(trim(a.short_name)) = lower(trim(b.short_name))
     AND ST_Intersects(a.geom, b.geom)
""")


def cluster_transport_stops(session):
    """
    Writes `transport_stops.cluster_id`. Returns the clusters of several stops:
    [(anchor, [(member, meters)])] to check them.
    """
    stops = {
        pk: {'name': name, 'codes': set(codes), 'departures': int(departures)}
        for pk, name, codes, departures in session.execute(_STOPS)
    }
    pairs = [
        (a, b, float(meters)) for a, b, meters in session.execute(
            _STOP_PAIRS, {'distance': NEAR_DISTANCE})
    ]
    clusters = cluster_stops(stops, pairs)
    distances = {
        (min(a, b), max(a, b)): meters for a, b, meters in pairs}

    session.execute(text("""
        UPDATE guidebook.transport_stops SET cluster_id = stop_pk
        WHERE cluster_id IS DISTINCT FROM stop_pk
    """))
    members = [
        {'pk': pk, 'cluster': anchor}
        for pk, anchor in clusters.items() if pk != anchor
    ]
    if members:
        session.execute(text("""
            UPDATE guidebook.transport_stops SET cluster_id = :cluster
            WHERE stop_pk = :pk
        """), members)

    grouped = defaultdict(list)
    for member in members:
        pk, anchor = member['pk'], member['cluster']
        grouped[anchor].append((pk, distances[(min(pk, anchor),
                                               max(pk, anchor))]))
    log.info('%d stops grouped in %d clusters (%d stops)',
             len(members), len(grouped), len(stops))
    return [
        (anchor, [(pk, stops[pk]['name'], meters) for pk, meters in group],
         stops[anchor]['name'])
        for anchor, group in grouped.items()
    ]


def hide_duplicate_lines(session):
    """
    Writes `transport_lines.duplicate_of`. Returns the hidden lines:
    {hidden: kept}.
    """
    lines = {
        line_id: {'trips': int(trips), 'length': float(meters or 0)}
        for line_id, trips, meters in session.execute(_LINES)
    }
    pairs = [
        (a, b, float(a_in_b or 0), float(b_in_a or 0))
        for a, b, a_in_b, b_in_a in session.execute(
            _LINE_PAIRS, {'tolerance': LINE_TOLERANCE})
    ]
    hidden = duplicate_lines(lines, pairs)

    session.execute(text("""
        UPDATE guidebook.transport_lines SET duplicate_of = NULL
        WHERE duplicate_of IS NOT NULL
    """))
    if hidden:
        session.execute(text("""
            UPDATE guidebook.transport_lines SET duplicate_of = :kept
            WHERE line_id = :hidden
        """), [{'hidden': h, 'kept': k} for h, k in hidden.items()])
    log.info('%d lines hidden as duplicates', len(hidden))
    return hidden
