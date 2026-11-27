"""The documents of camptocamp that a public transport stop leads to.

The stop areas imported from Navitia (guidebook.stopareas) are linked to the
waypoints they are near (waypoints_stopareas). The routes are associated with
those waypoints, and the outings with the routes.
"""

from sqlalchemy import func

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea

MAX_ITEMS = 10
# the stops of a long line lead to many documents: look at the nearest waypoints
MAX_WAYPOINTS = 50
MAX_NAVITIA_IDS = 500


def get_titles(session, document_ids, lang):
    """Title of documents, in the given language when there is one."""
    if not document_ids:
        return {}
    rows = (
        session.query(
            DocumentLocale.document_id, DocumentLocale.lang, DocumentLocale.title
        )
        .filter(DocumentLocale.document_id.in_(document_ids))
        .order_by(DocumentLocale.document_id, DocumentLocale.lang)
        .all()
    )
    titles = {}
    for document_id, locale_lang, title in rows:
        if locale_lang == lang or document_id not in titles:
            titles[document_id] = title
    return titles


def get_linked_documents(session, navitia_ids, lang, limit=MAX_ITEMS):
    """Waypoints, routes and outings reached from stop areas of Navitia."""
    ids = list(dict.fromkeys(i for i in navitia_ids if i))[:MAX_NAVITIA_IDS]
    result = {'waypoints': [], 'waypoint_ids': [], 'routes': [], 'outings': []}
    if not ids:
        return result

    distance = func.min(WaypointStoparea.distance)
    waypoints = (
        session.query(WaypointStoparea.waypoint_id, distance)
        .join(Stoparea, Stoparea.stoparea_id == WaypointStoparea.stoparea_id)
        .filter(Stoparea.navitia_id.in_(ids))
        .group_by(WaypointStoparea.waypoint_id)
        .order_by(distance, WaypointStoparea.waypoint_id)
        .limit(MAX_WAYPOINTS)
        .all()
    )
    if not waypoints:
        return result
    waypoint_ids = [waypoint_id for waypoint_id, _ in waypoints]

    route_ids = [
        route_id
        for (route_id,) in session.query(Association.child_document_id)
        .filter(
            Association.parent_document_id.in_(waypoint_ids),
            Association.child_document_type == ROUTE_TYPE,
        )
        .distinct()
    ]

    outing_counts = {}
    outings = []
    if route_ids:
        outing_counts = dict(
            session.query(Association.parent_document_id, func.count())
            .filter(
                Association.parent_document_id.in_(route_ids),
                Association.child_document_type == OUTING_TYPE,
            )
            .group_by(Association.parent_document_id)
            .all()
        )
        outings = (
            session.query(Association.child_document_id, Outing.date_end)
            .join(Outing, Outing.document_id == Association.child_document_id)
            .filter(
                Association.parent_document_id.in_(route_ids),
                Association.child_document_type == OUTING_TYPE,
            )
            .order_by(Outing.date_end.desc(), Outing.document_id.desc())
            .limit(limit)
            .all()
        )

    # the routes people go on most come first
    routes = sorted(route_ids, key=lambda i: (-outing_counts.get(i, 0), -i))[:limit]
    shown_waypoints = waypoints[:limit]

    titles = get_titles(
        session,
        [i for i, _ in shown_waypoints] + routes + [i for i, _ in outings],
        lang,
    )
    # all of them, nearest first: the lists of routes and outings filter on them
    result['waypoint_ids'] = waypoint_ids
    result['waypoints'] = [
        {
            'document_id': waypoint_id,
            'title': titles.get(waypoint_id),
            'distance': round(waypoint_distance, 2),
        }
        for waypoint_id, waypoint_distance in shown_waypoints
    ]
    result['routes'] = [
        {'document_id': route_id, 'title': titles.get(route_id)} for route_id in routes
    ]
    result['outings'] = [
        {
            'document_id': outing_id,
            'title': titles.get(outing_id),
            'date_end': date_end.isoformat(),
        }
        for outing_id, date_end in outings
    ]
    return result
