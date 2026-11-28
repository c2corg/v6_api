"""Store the routes of the partner outings (`partner_routes`) and their links.

The adapters give an outing the route(s) it followed (`HarvestedOuting.routes`)
when the site has a route of its own (skitour.fr topos, gulliver.it
itineraries, bivouak.net topos, gipfelbuch.ch routes). After the outings are
upserted, the job upserts their routes by `(source, external_id)`, so that the
outings of one route share a row, and links each outing to its routes
(`partner_outing_routes`).
"""

from sqlalchemy import delete, func, null, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from c2corg_api.models.partner_outing import (
    PartnerOuting,
    PartnerOutingRoute,
    PartnerRoute,
)

BATCH_SIZE = 500
# the fields of a route a later sighting fills when an earlier one had none
_OPTIONAL = ('url', 'summit_name', 'elevation_max', 'lon', 'lat')


def _merge(routes):
    """Return one dict per route, the fields of all its sightings in the run.

    The first sighting gives the title; a field it lacks is taken from a later
    one (the url of a gipfelbuch route is only on some of its reports).
    """
    merged = {}
    for source, route in routes:
        key = (source, route.external_id)
        values = merged.get(key)
        if values is None:
            merged[key] = {
                'source': source,
                'external_id': route.external_id,
                'title': route.title,
                'geom_quality': route.geom_quality,
                **{name: getattr(route, name) for name in _OPTIONAL},
            }
            continue
        for name in _OPTIONAL:
            if values[name] is None and getattr(route, name) is not None:
                values[name] = getattr(route, name)
                if name == 'lon':
                    values['geom_quality'] = route.geom_quality
    return list(merged.values())


def _row(values, now):
    lon, lat = values.pop('lon'), values.pop('lat')
    if lon is not None and lat is not None:
        geom = func.ST_Transform(
            func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), 3857
        )
    else:
        geom = null()
        values['geom_quality'] = 'none'
    return {**values, 'geom': geom, 'fetched_at': now}


def _upsert_batch(session, routes, now):
    """Upsert the routes; return {(source, external_id): id}."""
    statement = insert(PartnerRoute).values([_row(dict(r), now) for r in routes])
    stored = PartnerRoute.__table__.c
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        constraint='uq_partner_routes_source_external_id',
        set_={
            'title': excluded.title,
            'url': func.coalesce(excluded.url, stored.url),
            'summit_name': func.coalesce(excluded.summit_name, stored.summit_name),
            'elevation_max': func.coalesce(
                excluded.elevation_max, stored.elevation_max
            ),
            'geom': func.coalesce(excluded.geom, stored.geom),
            'geom_quality': func.coalesce(
                func.nullif(excluded.geom_quality, 'none'), stored.geom_quality
            ),
            'fetched_at': excluded.fetched_at,
        },
    ).returning(PartnerRoute.id, PartnerRoute.source, PartnerRoute.external_id)
    return {(row.source, row.external_id): row.id for row in session.execute(statement)}


def _outing_ids(session, keys):
    """Return {(source, external_id): id} of the stored outings."""
    rows = session.execute(
        select(PartnerOuting.id, PartnerOuting.source, PartnerOuting.external_id).where(
            tuple_(PartnerOuting.source, PartnerOuting.external_id).in_(keys)
        )
    )
    return {(row.source, row.external_id): row.id for row in rows}


def upsert_routes(session, outings, now):
    """Upsert the routes of the outings and link the outings to them.

    The outings must be stored already. A known route keeps its id and
    `first_seen_at`; its title is updated, and a field the new sighting lacks
    (url, summit, elevation, position) keeps its stored value. The links of an
    outing that names routes are replaced by those of this run; an outing that
    names none this run keeps its links (its detail page may just not have been
    read this time). Returns the number of routes upserted. Does not commit.
    """
    # one statement cannot update a row twice: the last occurrence wins, as in
    # upsert_outings
    unique = {(o.source, o.external_id): o for o in outings if o.routes}
    if not unique:
        return 0
    routes = _merge((o.source, route) for o in unique.values() for route in o.routes)
    route_ids = {}
    for start in range(0, len(routes), BATCH_SIZE):
        route_ids.update(
            _upsert_batch(session, routes[start : start + BATCH_SIZE], now)
        )

    keys = list(unique)
    outing_ids = {}
    for start in range(0, len(keys), BATCH_SIZE):
        outing_ids.update(_outing_ids(session, keys[start : start + BATCH_SIZE]))
    links = {}
    for key, outing in unique.items():
        outing_id = outing_ids.get(key)
        if outing_id is None:
            continue
        for position, route in enumerate(outing.routes):
            route_id = route_ids[(outing.source, route.external_id)]
            links.setdefault((outing_id, route_id), position)
    session.execute(
        delete(PartnerOutingRoute).where(
            PartnerOutingRoute.outing_id.in_(list(outing_ids.values()))
        )
    )
    if links:
        session.execute(
            insert(PartnerOutingRoute).values(
                [
                    {'outing_id': o, 'route_id': r, 'position': p}
                    for (o, r), p in links.items()
                ]
            )
        )
    return len(route_ids)
