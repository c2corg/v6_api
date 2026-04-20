"""
Domain-specific helpers for updating linked attributes across document types.

Extracted from ``c2corg_api.views.waypoint``, ``c2corg_api.views.route``,
and ``c2corg_api.views.area`` so that routers have no dependency on
``views/``.
"""

from itertools import combinations

from sqlalchemy import and_, case, column, func, literal_column, or_, text, union
from sqlalchemy.orm import joinedload, load_only

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation, update_area
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import update_cache_version_for_area
from c2corg_api.models.common.attributes import PublicTransportationRatings
from c2corg_api.models.document import DocumentGeometry, DocumentLocale, UpdateType
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.utils import get_mid_point
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.routers.helpers.document_helpers import get_best_locale
from c2corg_api.routers.helpers.document_listings import get_documents_for_ids
from c2corg_api.routers.helpers.document_schemas import outing_documents_config
from c2corg_api.routers.helpers.validation import get_first_column
from c2corg_api.search.advanced_search import get_all_filtered_docs

NUM_RECENT_OUTINGS = 10


# ── Route title-prefix helpers ───────────────────────────────


def set_route_title_prefix(route, waypoint_locales, waypoint_locales_index):
    """Sets the ``title_prefix`` of all locales of *route* using the
    provided waypoint locales.
    """
    if len(waypoint_locales) == 1:
        _set_title_prefix(route, waypoint_locales[0].title)
    else:
        for locale in route.locales:
            waypoint_locale = get_best_locale(waypoint_locales_index, locale.lang)
            _set_title_prefix_for_ids(
                [locale.id], waypoint_locale.title if waypoint_locale else ''
            )


def _set_title_prefix(route, title):
    _set_title_prefix_for_ids([locale.id for locale in route.locales], title)


def _set_title_prefix_for_ids(ids, title):
    resolve_db(None).query(RouteLocale).filter(RouteLocale.id.in_(ids)).update(
        {RouteLocale.title_prefix: title}, synchronize_session=False
    )


def check_title_prefix(route, create=False):
    """Resolve and set ``title_prefix`` for *route* from its main waypoint."""
    if route.main_waypoint_id is None and not create:
        _set_title_prefix(route, '')
    else:
        waypoint_locales = (
            resolve_db(None)
            .query(DocumentLocale)
            .filter(DocumentLocale.document_id == route.main_waypoint_id)
            .options(load_only(DocumentLocale.lang, DocumentLocale.title))
            .all()
        )
        waypoint_locales_index = {locale.lang: locale for locale in waypoint_locales}
        set_route_title_prefix(route, waypoint_locales, waypoint_locales_index)


# ── Public-transportation rating helpers ─────────────────────


def update_pt_rating(route, waypoint_extrapolation=True):
    """Update public transportation rating based on linked access waypoints."""
    if waypoint_extrapolation:
        linked_access_waypoints = _get_linked_waypoints_pt_ratings(route)
        starting_waypoints, ending_waypoints = _find_starting_and_ending_points(
            linked_access_waypoints, route.route_types
        )
    else:
        starting_waypoints, ending_waypoints = [], []

    public_transportation_rating = _pt_rating(
        starting_waypoints, ending_waypoints, route.route_types
    )

    resolve_db(None).query(Route).filter(Route.document_id == route.document_id).update(
        {Route.public_transportation_rating: public_transportation_rating},
        synchronize_session=False,
    )


def _get_linked_waypoints_pt_ratings(route):
    waypoint_type = text("'" + WAYPOINT_TYPE + "'")
    return (
        resolve_db(None)
        .query(Waypoint)
        .select_from(Association)
        .filter(
            or_(
                Association.parent_document_id == route.document_id,
                Association.child_document_id == route.document_id,
            )
        )
        .filter(
            or_(
                Association.child_document_type == waypoint_type,
                Association.parent_document_type == waypoint_type,
            )
        )
        .join(
            Waypoint,
            or_(
                Waypoint.document_id == Association.child_document_id,
                Waypoint.document_id == Association.parent_document_id,
            ),
        )
        .filter(Waypoint.waypoint_type == 'access')
        .all()
    )


def _find_starting_and_ending_points(waypoints, route_types):
    if route_types and bool(
        set(['loop', 'loop_hut', 'return_same_way']) & set(route_types)
    ):
        return waypoints, []
    elif (
        route_types
        and bool(set(['traverse', 'raid', 'expedition']) & set(route_types))
        and len(waypoints) >= 2
    ):
        if len(waypoints) == 2:
            return [waypoints[0]], [waypoints[1]]
        max_dist = 0
        most_distant_points = None
        for w1, w2 in combinations(waypoints, 2):
            dist = w1.geometry.distance(w1.geometry.geom, w2.geometry.geom)
            if dist > max_dist:
                max_dist = dist
                most_distant_points = (w1, w2)
        return [most_distant_points[0]], [most_distant_points[1]]
    elif len(waypoints) == 1:
        return [waypoints[0]], []
    else:
        return [], []


def _pt_rating(starting_waypoints, ending_waypoints, route_types):
    _rank = {r.value: i for i, r in enumerate(PublicTransportationRatings)}
    default_rating = 'unknown service'
    worst_rating = 'no service'

    def best(a, b):
        return a if _rank[a] <= _rank[b] else b

    def worst(a, b):
        return a if _rank[a] >= _rank[b] else b

    if len(starting_waypoints) == 0:
        return default_rating

    best_starting = worst_rating
    for waypoint in starting_waypoints:
        rating = waypoint.public_transportation_rating or default_rating
        best_starting = best(best_starting, rating)

    if not (
        route_types and bool(set(['traverse', 'raid', 'expedition']) & set(route_types))
    ):
        return best_starting

    if len(ending_waypoints) == 0:
        return default_rating

    best_ending = worst_rating
    for waypoint in ending_waypoints:
        rating = waypoint.public_transportation_rating or default_rating
        best_ending = best(best_ending, rating)

    return worst(best_starting, best_ending)


# ── Route-level linked-attribute functions ───────────────────


def init_linked_attributes(route, user_id):
    """Initialise title prefix and PT rating for a new route."""
    check_title_prefix(route, create=True)
    update_pt_rating(route)


def update_linked_attributes(route, update_types, user_id):
    """Re-check title prefix and PT rating on route update."""
    check_title_prefix(route)
    update_pt_rating(route)


def update_default_geometry(route, route_in):
    """Copy geometry from the old route when the new payload omits it."""
    geometry = route.geometry
    geometry_in = route_in.geometry

    if geometry_in is None:
        route_in.geometry = route.geometry
    elif geometry_in.geom is None and geometry is not None:
        geometry_in.geom = geometry.geom


def set_default_geometry(linked_waypoints, route, user_id):
    """Set the default geometry for a newly created route."""
    from c2corg_api.routers.helpers.document_crud import (
        set_default_geom_from_associations,
    )

    if route.geometry is not None and route.geometry.geom is not None:
        return

    if route.geometry is not None and route.geometry.geom_detail is not None:
        route.geometry.geom = get_mid_point(route.geometry.geom_detail)
    elif route.main_waypoint_id:
        main_wp_point = (
            resolve_db(None)
            .query(DocumentGeometry.geom)
            .filter(DocumentGeometry.document_id == route.main_waypoint_id)
            .scalar()
        )
        if main_wp_point is not None:
            route.geometry = DocumentGeometry(geom=main_wp_point)

    set_default_geom_from_associations(route, linked_waypoints)


def update_all_pt_rating(waypoint_extrapolation=True):
    """Update the public transportation rating of every route."""
    route_type = text("'" + ROUTE_TYPE + "'")
    waypoint_type = text("'" + WAYPOINT_TYPE + "'")

    parent_routes = (
        resolve_db(None)
        .query(Association.parent_document_id.label('route_id'))
        .filter(Association.parent_document_type == route_type)
        .filter(Association.child_document_type == waypoint_type)
        .join(Waypoint, Waypoint.document_id == Association.child_document_id)
        .filter(Waypoint.waypoint_type == 'access')
        .subquery()
    )
    children_routes = (
        resolve_db(None)
        .query(Association.child_document_id.label('route_id'))
        .filter(Association.child_document_type == route_type)
        .filter(Association.parent_document_type == waypoint_type)
        .join(Waypoint, Waypoint.document_id == Association.parent_document_id)
        .filter(Waypoint.waypoint_type == 'access')
        .subquery()
    )
    merged = union(parent_routes.select(), children_routes.select()).subquery()
    routes = (
        resolve_db(None)
        .query(Route)
        .select_from(merged)
        .join(Route, Route.document_id == column('route_id'))
        .all()
    )

    for route in routes:
        update_pt_rating(route, waypoint_extrapolation)

    return True


def set_recent_outings(route, lang):
    """Set last 10 outings on the given route."""
    recent_outing_ids = get_first_column(
        resolve_db(None)
        .query(Outing.document_id, Outing.date_end)
        .filter(Outing.redirects_to.is_(None))
        .join(Association, Outing.document_id == Association.child_document_id)
        .filter(Association.parent_document_id == route.document_id)
        .distinct()
        .order_by(Outing.date_end.desc())
        .limit(NUM_RECENT_OUTINGS)
        .all()
    )

    total = (
        resolve_db(None)
        .query(Outing.document_id)
        .filter(Outing.redirects_to.is_(None))
        .join(Association, Outing.document_id == Association.child_document_id)
        .filter(Association.parent_document_id == route.document_id)
        .distinct()
        .count()
    )

    route.associations['recent_outings'] = get_documents_for_ids(
        recent_outing_ids, lang, outing_documents_config, total, db=resolve_db(None)
    )


# ── Waypoint-level linked-attribute functions ────────────────


def update_linked_routes(waypoint, update_types, user_id):
    """Propagate waypoint changes to linked routes."""
    update_linked_route_titles(waypoint, update_types, user_id)
    _update_linked_routes_public_transportation_rating(waypoint, update_types)


def update_linked_route_titles(waypoint, update_types, user_id):
    """Update ``title_prefix`` on routes whose main waypoint is *waypoint*."""
    if UpdateType.LANG not in update_types:
        return

    linked_routes = (
        resolve_db(None)
        .query(Route)
        .filter(Route.main_waypoint_id == waypoint.document_id)
        .options(
            joinedload(Route.locales).load_only(DocumentLocale.lang, DocumentLocale.id)
        )
        .options(load_only(Route.document_id))
        .all()
    )

    if linked_routes:
        waypoint_locales = waypoint.locales
        waypoint_locales_index = {locale.lang: locale for locale in waypoint_locales}

        for route in linked_routes:
            set_route_title_prefix(route, waypoint_locales, waypoint_locales_index)


def _update_linked_routes_public_transportation_rating(waypoint, update_types):
    if (
        waypoint.waypoint_type != 'access'
        or 'public_transportation_rating' not in update_types
    ):
        return

    route_type = text("'" + ROUTE_TYPE + "'")

    parent_routes = (
        resolve_db(None)
        .query(Association.parent_document_id.label('route_id'))
        .filter(Association.parent_document_type == route_type)
        .filter(Association.child_document_id == waypoint.document_id)
        .subquery()
    )
    children_routes = (
        resolve_db(None)
        .query(Association.child_document_id.label('route_id'))
        .filter(Association.child_document_type == route_type)
        .filter(Association.parent_document_id == waypoint.document_id)
        .subquery()
    )
    merged = union(parent_routes.select(), children_routes.select()).subquery()
    routes = (
        resolve_db(None)
        .query(Route)
        .select_from(merged)
        .join(Route, Route.document_id == column('route_id'))
        .all()
    )

    for route in routes:
        update_pt_rating(route)


# ── Area-level association update ────────────────────────────


def update_area_associations(area, update_types, user_id):
    """Update area ↔ document links when the area geometry has changed."""
    if update_types:
        update_cache_version_for_area(area)

    if UpdateType.GEOM in update_types:
        update_area(area, reset=True)


# ── Reachable queries (navitia) ──────────────────────────────


def get_waypoints_reachable_ids():
    """Get all waypoint IDs that have a stop-area link."""
    all_wp = (
        resolve_db(None)
        .query(Waypoint)
        .join(WaypointStoparea, WaypointStoparea.waypoint_id == Waypoint.document_id)
        .distinct()
        .all()
    )
    return {r.document_id for r in all_wp}


def build_reachable_waypoints_query(params, meta_params):
    """Build a waypoints query for reachable (public transport) waypoints."""
    all_filtered_ids, total_hits = get_all_filtered_docs(
        params, meta_params, get_waypoints_reachable_ids(), WAYPOINT_TYPE
    )

    if total_hits == 0:
        return None, 0

    ordering_case = case(
        {doc_id: idx for idx, doc_id in enumerate(all_filtered_ids)},
        value=Waypoint.document_id,
    )

    query = (
        resolve_db(None)
        .query(
            Waypoint,
            func.jsonb_agg(
                func.distinct(
                    func.jsonb_build_object(
                        literal_column("'document_id'"), Area.document_id
                    )
                )
            ).label('areas'),
        )
        .filter(Waypoint.document_id.in_(all_filtered_ids))
        .join(AreaAssociation, AreaAssociation.document_id == Waypoint.document_id)
        .join(Area, Area.document_id == AreaAssociation.area_id)
        .group_by(Waypoint)
        .order_by(ordering_case)
    )

    return query, total_hits


def get_routes_reachable_ids():
    """Get all route IDs reachable via access waypoints with stop-areas."""
    all_routes = (
        resolve_db(None)
        .query(Route)
        .join(
            Association,
            or_(
                Association.child_document_id == Route.document_id,
                Association.parent_document_id == Route.document_id,
            ),
        )
        .join(
            Waypoint,
            and_(
                or_(
                    Waypoint.document_id == Association.child_document_id,
                    Waypoint.document_id == Association.parent_document_id,
                ),
                Waypoint.waypoint_type == 'access',
            ),
        )
        .join(WaypointStoparea, WaypointStoparea.waypoint_id == Waypoint.document_id)
        .distinct()
        .all()
    )
    return {r.document_id for r in all_routes}


def build_reachable_route_query_with_waypoints(params, meta_params):
    """Build a routes query including associated waypoints for navitia."""
    all_filtered_ids, total_hits = get_all_filtered_docs(
        params, meta_params, get_routes_reachable_ids(), ROUTE_TYPE
    )

    if total_hits == 0:
        return None, 0

    ordering_case = case(
        {doc_id: idx for idx, doc_id in enumerate(all_filtered_ids)},
        value=Route.document_id,
    )

    query = (
        resolve_db(None)
        .query(
            Route,
            func.jsonb_agg(
                func.distinct(
                    func.jsonb_build_object(
                        literal_column("'document_id'"), Area.document_id
                    )
                )
            ).label('areas'),
            func.jsonb_agg(
                func.distinct(
                    func.jsonb_build_object(
                        literal_column("'document_id'"), Waypoint.document_id
                    )
                )
            ).label('waypoints'),
        )
        .select_from(Association)
        .join(
            Route,
            and_(
                or_(
                    Route.document_id == Association.child_document_id,
                    Route.document_id == Association.parent_document_id,
                ),
                Route.document_id.in_(all_filtered_ids),
            ),
        )
        .join(AreaAssociation, AreaAssociation.document_id == Route.document_id)
        .join(Area, Area.document_id == AreaAssociation.area_id)
        .join(
            Waypoint,
            and_(
                or_(
                    Waypoint.document_id == Association.child_document_id,
                    Waypoint.document_id == Association.parent_document_id,
                ),
                Waypoint.waypoint_type == 'access',
            ),
        )
        .join(WaypointStoparea, WaypointStoparea.waypoint_id == Waypoint.document_id)
        .group_by(Route)
        .order_by(ordering_case)
    )

    return query, total_hits
