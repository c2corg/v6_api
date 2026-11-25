"""Locate the partner outings published without coordinates.

Some sites give no position (gipfelbuch, skitourenportal, bivouak beyond its
lookup cap), only hints: `summit_name` (+ `elevation_max`), `region` and
`country` (`HarvestedOuting`). Before storing, the job resolves them, in order:

1. the summit against the c2c waypoints (summits and passes): same folded name
   (`partners.places`), altitude within `ALTITUDE_TOLERANCE` when the partner
   gives one, inside the country area when it gives one. Several candidates is
   no match. Result: the point of the waypoint, `geom_quality='summit_match'`
   (a guess by name, where `summit` is a point the partner gave), and the areas
   of that point (`assign_areas`).
2. the region through the table of the source (`partners/regions/<source>.json`):
   the centroid of its first area (`geom_quality='area_centroid'`), and the areas
   of the table (plus the country), not those of the centroid.
3. the country alone: no point, the country area only.

Each resolution is cached in `partner_lookups` (`resolve:summit:...`,
`resolve:area:<id>`), misses too, and expires with the other lookups
(`partners.lookup_retention_days`). The uncached summits of a run are looked up
with one query.
"""

import dataclasses
import hashlib
import logging
from collections import Counter, defaultdict

from sqlalchemy import text

from c2corg_api.models import schema
from c2corg_api.partners import places, region_map

log = logging.getLogger(__name__)

ALTITUDE_TOLERANCE = 50  # metres
# the waypoint types a partner may call a summit (a tour often ends at a pass)
SUMMIT_TYPES = ('summit', 'pass')
KEY_LENGTH = 128  # partner_lookups.key


@dataclasses.dataclass(frozen=True, slots=True)
class _Hint:
    full: str
    short: str
    altitude: int | None
    country_area: int | None
    country: str

    @property
    def cache_key(self):
        name = self.full
        tail = f'|{self.altitude or ""}|{self.country}'
        room = KEY_LENGTH - len('resolve:summit:') - len(tail)
        if len(name) > room:
            digest = hashlib.sha1(name.encode()).hexdigest()[:10]
            name = f'{name[: room - 11]}~{digest}'
        return f'resolve:summit:{name}{tail}'


def resolve_locations(session, lookups, outings):
    """Locate the outings without coordinates from their hints.

    Return `(outings, area_ids, counts)`: the outings (the located ones
    replaced, with lon/lat and their `geom_quality`), the preset `area_ids`
    by `(source, external_id)` (the outings located by region or country: their
    areas do not come from a point), and a Counter of the outcomes. Does not
    commit; writes the lookups.
    """
    counts = Counter()
    hints = {}
    for outing in outings:
        if outing.lon is None or outing.lat is None:
            hint = _hint(outing)
            if hint is not None:
                hints[hint] = None
    summits = _summits(session, lookups, list(hints))

    located = []
    area_ids = {}
    for outing in outings:
        if outing.lon is not None and outing.lat is not None:
            located.append(outing)
            continue
        hint = _hint(outing)
        place = summits.get(hint) if hint else None
        if place:
            counts['summit_match'] += 1
            located.append(
                dataclasses.replace(
                    outing,
                    lon=place['lon'],
                    lat=place['lat'],
                    geom_quality='summit_match',
                )
            )
            continue
        region = region_map.lookup(outing.source, outing.region)
        country_area = region_map.country_area(
            outing.country or (region.country if region else None)
        )
        centroid = (
            _area_centroid(session, lookups, region.area_ids[0])
            if region and region.area_ids
            else None
        )
        if centroid:
            counts['area_centroid'] += 1
            ids = list(region.area_ids)
            if country_area is not None and country_area not in ids:
                ids.append(country_area)
            area_ids[(outing.source, outing.external_id)] = sorted(ids)
            located.append(
                dataclasses.replace(
                    outing,
                    lon=centroid['lon'],
                    lat=centroid['lat'],
                    geom_quality='area_centroid',
                )
            )
            continue
        if country_area is not None:
            counts['country'] += 1
            area_ids[(outing.source, outing.external_id)] = [country_area]
        else:
            counts['unresolved'] += 1
        located.append(outing)
    return located, area_ids, counts


def _hint(outing):
    full, short = places.keys(outing.summit_name)
    if not full:
        return None
    altitude = outing.elevation_max if outing.elevation_max else None
    country = (outing.country or '').strip().upper()
    return _Hint(full, short, altitude, region_map.country_area(country), country)


def _summits(session, lookups, hints):
    """Return `{hint: {'lon', 'lat'} or None}`, from the cache or one query."""
    found = {}
    missing = []
    for hint in hints:
        cached = lookups.get(hint.cache_key)
        if cached is not None:
            found[hint] = cached if cached.get('waypoint_id') else None
        else:
            missing.append(hint)
    if not missing:
        return found
    candidates = _candidates(session, missing)
    for hint in missing:
        place = _pick(hint, candidates)
        found[hint] = place
        lookups.put(hint.cache_key, place or {'waypoint_id': None})
    log.info(
        'Partner summits: %d looked up, %d found',
        len(missing),
        sum(1 for h in missing if found[h]),
    )
    return found


def _pick(hint, candidates):
    """Return the one waypoint matching a hint, None when none or several do."""

    def keep(row):
        if hint.country_area is not None and hint.country_area not in row['countries']:
            return False
        if hint.altitude is None:
            return True
        return (
            row['elevation'] is not None
            and abs(row['elevation'] - hint.altitude) <= ALTITUDE_TOLERANCE
        )

    exact = {r['waypoint_id']: r for r in candidates['full'][hint.full] if keep(r)}
    if not exact and hint.altitude is not None:
        # "Pointe de la Galise" for "Galise": only when the altitude agrees
        exact = {
            r['waypoint_id']: r for r in candidates['short'][hint.short] if keep(r)
        }
    if len(exact) != 1:
        return None
    row = next(iter(exact.values()))
    return {'waypoint_id': row['waypoint_id'], 'lon': row['lon'], 'lat': row['lat']}


def _candidates(session, hints):
    """Return the waypoints named like the hints: `{'full'|'short': {key: [row]}}`.

    One scan for all the hints: the titles of the summits and passes (each part
    of "A / B" alone) are folded here (`places`, see there why not in SQL) and
    kept when a key of a hint matches; only the matches get their point and
    their country areas, by primary key and GiST index. When every hint has an
    altitude, only the waypoints within the tolerance of one are read.
    """
    fulls = {h.full for h in hints}
    shorts = {h.short for h in hints if h.altitude is not None}
    altitudes = {h.altitude for h in hints}
    params = {}
    sql = NAMES_SQL
    if None not in altitudes:
        sql += """
          AND w.elevation IS NOT NULL AND EXISTS (
              SELECT 1 FROM unnest(CAST(:altitudes AS integer[])) a
              WHERE w.elevation BETWEEN a - :tolerance AND a + :tolerance)"""
        params = {'altitudes': sorted(altitudes), 'tolerance': ALTITUDE_TOLERANCE}
    names = defaultdict(lambda: (set(), set()))
    elevations = {}
    for document_id, elevation, title in session.execute(text(sql), params):
        for part in title.split('/'):
            full, short = places.keys(part)
            if full in fulls or short in shorts:
                names[document_id][0].add(full)
                names[document_id][1].add(short)
                elevations[document_id] = elevation
    candidates = {'full': defaultdict(list), 'short': defaultdict(list)}
    if not names:
        return candidates
    for row in session.execute(text(POINTS_SQL), {'ids': sorted(names)}).mappings():
        document_id = row['document_id']
        entry = {
            'waypoint_id': document_id,
            'elevation': elevations[document_id],
            'lon': row['lon'],
            'lat': row['lat'],
            'countries': set(row['countries'] or ()),
        }
        full_keys, short_keys = names[document_id]
        for key in full_keys:
            candidates['full'][key].append(entry)
        for key in short_keys:
            candidates['short'][key].append(entry)
    return candidates


# the titles of the summit and pass waypoints (index on the locales' document_id)
NAMES_SQL = f"""
    SELECT w.document_id, w.elevation, l.title
    FROM {schema}.waypoints w
    JOIN {schema}.documents d
      ON d.document_id = w.document_id AND d.redirects_to IS NULL
    JOIN {schema}.documents_locales l ON l.document_id = w.document_id
    WHERE w.waypoint_type IN ({', '.join(f"'{t}'" for t in SUMMIT_TYPES)})"""

# the point and the country areas of a few waypoints
POINTS_SQL = f"""
    SELECT g.document_id,
           ST_X(ST_Transform(g.geom, 4326)) AS lon,
           ST_Y(ST_Transform(g.geom, 4326)) AS lat,
           ARRAY(
               SELECT a.document_id
               FROM {schema}.documents_geometries ag
               JOIN {schema}.areas a ON a.document_id = ag.document_id
               JOIN {schema}.documents ad
                 ON ad.document_id = a.document_id AND ad.redirects_to IS NULL
               WHERE a.area_type = 'country'
                 AND ST_Intersects(ag.geom_detail, g.geom)
           ) AS countries
    FROM {schema}.documents_geometries g
    WHERE g.document_id = ANY(:ids) AND g.geom IS NOT NULL"""


def _area_centroid(session, lookups, area_id):
    """Return `{'lon', 'lat'}` of the centroid of an area, None without geometry."""
    key = f'resolve:area:{area_id}'
    cached = lookups.get(key)
    if cached is not None:
        return cached if cached.get('lon') is not None else None
    row = session.execute(
        text(
            f"""
            SELECT ST_X(c) AS lon, ST_Y(c) AS lat FROM (
                SELECT ST_Transform(ST_Centroid(g.geom_detail), 4326) AS c
                FROM {schema}.documents_geometries g
                WHERE g.document_id = :id AND g.geom_detail IS NOT NULL
            ) x"""
        ),
        {'id': area_id},
    ).first()
    place = {'lon': row.lon, 'lat': row.lat} if row else None
    lookups.put(key, place or {'lon': None})
    return place
