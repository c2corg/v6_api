"""
Public transport on the maps: stops and lines located in a bbox (light, for
drawing), and the details of a stop or of a line (timetables, read on click).

The data comes from the GTFS feeds (`c2corg_api.transport`) and from the
Navitia stops of the waypoints (`guidebook.stopareas`).
"""
import json
import math

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.transport import (
    TransportFeed, TransportLine, TransportStop)
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.transport.merge import merge_details
from c2corg_api.views import cors_policy
from c2corg_api.views.validation import validate_id
from cornice.resource import resource, view
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import aliased

# safety nets: a very wide bbox could return a lot (a Navitia stop is stored
# once per line)
MAX_STOPAREAS_BY_BBOX = 5000
MAX_LINES_BY_BBOX = 500

# the data changes once a month
CACHE_CONTROL = 'public, max-age=86400'


def validate_bbox_param(request, **kwargs):
    """
    Checks that the optional `bbox` parameter is a valid
    `xmin,ymin,xmax,ymax` extent (EPSG:3857).
    """
    bbox = request.GET.get('bbox')
    if bbox is None:
        return

    try:
        values = [float(value) for value in bbox.split(',')]
    except ValueError:
        values = []

    if len(values) != 4 or not all(math.isfinite(v) for v in values) \
            or values[0] >= values[2] or values[1] >= values[3]:
        request.errors.add(
            'querystring', 'bbox',
            'invalid bbox, expected xmin,ymin,xmax,ymax (EPSG:3857)')
        return

    request.validated['bbox'] = values


def validate_required_bbox_param(request, **kwargs):
    validate_bbox_param(request)
    if 'bbox' not in request.validated and not request.errors:
        request.errors.add(
            'querystring', 'bbox',
            'bbox is required: xmin,ymin,xmax,ymax (EPSG:3857)')


def _feed_info(feed):
    return {
        'name': feed.name,
        'license': feed.license,
        'attribution': feed.attribution,
        'imported_at': feed.imported_at.isoformat()
        if feed.imported_at else None,
    }


def _nearest_waypoints(navitia_ids):
    """
    The waypoints the Navitia stops have been associated with, for each of
    the stops: {navitia_id: {waypoint_id: walking distance}}.
    """
    distances = {}
    if not navitia_ids:
        return distances
    links = DBSession.query(
        Stoparea.navitia_id,
        WaypointStoparea.waypoint_id,
        WaypointStoparea.distance
    ).join(
        WaypointStoparea,
        WaypointStoparea.stoparea_id == Stoparea.stoparea_id
    ).filter(Stoparea.navitia_id.in_(list(navitia_ids))).all()
    for navitia_id, waypoint_id, distance in links:
        by_waypoint = distances.setdefault(navitia_id, {})
        by_waypoint[waypoint_id] = min(
            distance, by_waypoint.get(waypoint_id, distance))
    return distances


def _waypoint_locales(waypoint_ids):
    """The titles of waypoints: {waypoint_id: [{lang, title}]}."""
    locales = {}
    if waypoint_ids:
        for document_id, lang, title in DBSession.query(
                DocumentLocale.document_id,
                DocumentLocale.lang,
                DocumentLocale.title
        ).filter(DocumentLocale.document_id.in_(waypoint_ids)):
            locales.setdefault(document_id, []).append(
                {'lang': lang, 'title': title})
    return locales


def _waypoints_payload(distances_by_waypoint, locales):
    """Waypoints, nearest first."""
    return [
        {
            'document_id': waypoint_id,
            'distance': round(distance, 2),
            'locales': locales.get(waypoint_id, [])
        }
        for waypoint_id, distance in sorted(
            distances_by_waypoint.items(), key=lambda item: item[1])
    ]


def _navitia_stops_in_bbox(envelope):
    """
    The Navitia stops of the bbox that are not matched with a GTFS stop, one
    entry per stop (it is stored once per line) with its lines and the
    waypoints it is associated with.
    """
    stopareas = (
        DBSession.query(Stoparea)
        .filter(func.ST_Intersects(Stoparea.geom, envelope))
        .order_by(Stoparea.stoparea_id)
        .limit(MAX_STOPAREAS_BY_BBOX)
        .all())
    if not stopareas:
        return []

    # one query using the index of `navitia_ids`, whatever the number of
    # GTFS stops
    navitia_ids = {s.navitia_id for s in stopareas}
    matched = {
        navitia_id for navitia_id, in DBSession.query(
            func.unnest(TransportStop.navitia_ids)
        ).filter(TransportStop.navitia_ids.overlap(list(navitia_ids)))
    } & navitia_ids
    stopareas = [s for s in stopareas if s.navitia_id not in matched]
    if not stopareas:
        return []

    distances = _nearest_waypoints({s.navitia_id for s in stopareas})
    locales = _waypoint_locales(
        {wid for by_wp in distances.values() for wid in by_wp})

    stops = {}  # navitia_id -> stop, insertion ordered
    for stoparea in stopareas:
        stop = stops.get(stoparea.navitia_id)
        if stop is None:
            stop = stops[stoparea.navitia_id] = {
                'kind': 'navitia',
                'navitia_id': stoparea.navitia_id,
                'stoparea_name': stoparea.stoparea_name,
                'coordinates': stoparea.to_dict()['coordinates'],
                'linked': True,
                'lines': [],
                'waypoints': _waypoints_payload(
                    distances.get(stoparea.navitia_id, {}), locales)
            }
        stop['lines'].append({
            'id': stoparea.stoparea_id,
            'line': stoparea.line,
            'operator': stoparea.operator
        })
    return list(stops.values())


def get_stops_in_bbox(bbox, include_all=False):
    """
    The stops located in the given bbox (EPSG:3857): the GTFS stops (only the
    ones linked to a waypoint unless `include_all`), and the Navitia stops
    that are not matched with a GTFS stop. Light: the details (timetables,
    waypoints of a GTFS stop) are read on click.
    """
    envelope = func.ST_MakeEnvelope(*bbox, 3857)
    # a cluster of stops of the same place is one stop, at its anchor, linked
    # to a waypoint if one of the stops is
    member = aliased(TransportStop)
    linked = exists().where(and_(
        member.cluster_id == TransportStop.stop_pk,
        func.cardinality(member.navitia_ids) > 0))
    query = DBSession.query(
        TransportStop.stop_pk,
        TransportStop.name,
        TransportStop.mode,
        func.ST_X(TransportStop.geom),
        func.ST_Y(TransportStop.geom),
        linked
    ).filter(
        func.ST_Intersects(TransportStop.geom, envelope)
    ).filter(TransportStop.cluster_id == TransportStop.stop_pk)
    if not include_all:
        query = query.filter(linked)
    gtfs_stops = [
        {
            'kind': 'gtfs',
            'id': stop_pk,
            'stoparea_name': name,
            'mode': mode,
            'coordinates': {'x': x, 'y': y},
            'linked': is_linked,
        }
        for stop_pk, name, mode, x, y, is_linked in query
        .order_by(TransportStop.stop_pk)
        .limit(MAX_STOPAREAS_BY_BBOX)
    ]
    return gtfs_stops + _navitia_stops_in_bbox(envelope)


@resource(collection_path='/transport-lines', path='/transport-lines/{id}',
          cors_policy=cors_policy)
class TransportLineRest:

    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_required_bbox_param])
    def collection_get(self):
        """
        Get the lines located in a bbox, with their path.

        `bbox=xmin,ymin,xmax,ymax`
        A search bbox in EPSG:3857.

        The paths are simplified (5 m) and merged: one geometry per line.
        """
        envelope = func.ST_MakeEnvelope(*self.request.validated['bbox'], 3857)
        rows = DBSession.query(
            TransportLine.line_id,
            TransportLine.short_name,
            TransportLine.long_name,
            TransportLine.mode,
            TransportLine.color,
            TransportLine.text_color,
            func.ST_AsGeoJSON(TransportLine.geom, 1)
        ).filter(
            func.ST_Intersects(TransportLine.geom, envelope)
        ).filter(
            TransportLine.duplicate_of.is_(None)
        ).order_by(TransportLine.line_id).limit(MAX_LINES_BY_BBOX).all()

        self.request.response.headers['Cache-Control'] = CACHE_CONTROL
        return {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'id': line_id,
                    'geometry': json.loads(geometry),
                    'properties': {
                        'line_id': line_id,
                        'short_name': short_name,
                        'long_name': long_name,
                        'mode': mode,
                        'color': color,
                        'text_color': text_color,
                    }
                }
                for (line_id, short_name, long_name, mode, color, text_color,
                     geometry) in rows
            ]
        }

    @view(validators=[validate_id])
    def get(self):
        """
        Get a line: directions, stops in order and timetable.
        """
        line = DBSession.query(TransportLine).get(
            self.request.matchdict['id'])
        if line is not None and line.duplicate_of is not None:
            # a hidden line (it may be the one of a timetable)
            line = DBSession.query(TransportLine).get(
                line.duplicate_of) or line
        if line is None:
            self.request.response.status = 404
            return {'error': 'Line not found'}
        feed = DBSession.query(TransportFeed).get(line.feed_id)

        details = line.details
        stop_ids = {
            stop['stop_id']
            for direction in details['directions']
            for stop in direction['stops']
        }
        # the stop of a cluster is its anchor
        stops = {
            stop_id: (cluster_id or stop_pk, is_linked)
            for stop_id, stop_pk, cluster_id, is_linked in DBSession.query(
                TransportStop.stop_id,
                TransportStop.stop_pk,
                TransportStop.cluster_id,
                func.cardinality(TransportStop.navitia_ids) > 0
            ).filter(TransportStop.feed_id == line.feed_id)
            .filter(TransportStop.stop_id.in_(stop_ids))
        }
        cluster_ids = {cluster_id for cluster_id, _ in stops.values()}
        linked_clusters = {
            cluster_id for cluster_id, in DBSession.query(
                TransportStop.cluster_id
            ).filter(TransportStop.cluster_id.in_(cluster_ids))
            .filter(func.cardinality(TransportStop.navitia_ids) > 0)
        } if cluster_ids else set()
        for direction in details['directions']:
            for stop in direction['stops']:
                stop_pk, is_linked = stops.get(stop['stop_id'], (None, False))
                stop['stop_pk'] = stop_pk
                stop['linked'] = is_linked or stop_pk in linked_clusters

        self.request.response.headers['Cache-Control'] = CACHE_CONTROL
        return {
            'line_id': line.line_id,
            'short_name': line.short_name,
            'long_name': line.long_name,
            'mode': line.mode,
            'color': line.color,
            'text_color': line.text_color,
            'operator': line.operator,
            'url': line.url,
            'feed': _feed_info(feed),
            'details': details,
        }


@resource(path='/transport-stops/{id}', cors_policy=cors_policy)
class TransportStopRest:

    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_id])
    def get(self):
        """
        Get a stop: the timetable of its lines, and the waypoints it has been
        associated with (nearest first).
        """
        stop = DBSession.query(TransportStop).get(
            self.request.matchdict['id'])
        if stop is None:
            self.request.response.status = 404
            return {'error': 'Stop not found'}
        # a stop of a cluster shows the timetable of the whole cluster, from
        # its anchor
        anchor_id = stop.cluster_id or stop.stop_pk
        members = DBSession.query(TransportStop).filter(
            TransportStop.cluster_id == anchor_id
        ).order_by(TransportStop.stop_pk).all() or [stop]
        members.sort(key=lambda member: member.stop_pk != anchor_id)
        anchor = members[0]

        feeds = []
        for member in members:
            if member.feed_id not in feeds:
                feeds.append(member.feed_id)
        feed_infos = [
            _feed_info(DBSession.query(TransportFeed).get(feed_id))
            for feed_id in feeds]

        details = merge_details(
            [(member.feed_id, member.details) for member in members])
        # the line of a hidden duplicate is the line it is a duplicate of
        line_ids = {
            (feed_id, route_id): duplicate_of or line_id
            for feed_id, route_id, line_id, duplicate_of in DBSession.query(
                TransportLine.feed_id, TransportLine.route_id,
                TransportLine.line_id, TransportLine.duplicate_of
            ).filter(TransportLine.feed_id.in_(feeds))
            .filter(TransportLine.route_id.in_(
                [line['route_id'] for line in details['lines']]))
        }
        for line in details['lines']:
            line['line_id'] = line_ids.get(
                (line.pop('feed_id'), line['route_id']))

        navitia_ids = {
            navitia_id for member in members
            for navitia_id in member.navitia_ids}
        distances = {}
        for by_waypoint in _nearest_waypoints(navitia_ids).values():
            for waypoint_id, distance in by_waypoint.items():
                distances[waypoint_id] = min(
                    distance, distances.get(waypoint_id, distance))

        self.request.response.headers['Cache-Control'] = CACHE_CONTROL
        return {
            'id': anchor.stop_pk,
            'stoparea_name': anchor.name,
            'mode': anchor.mode,
            # the feeds of the stops of the cluster, the first one is the
            # one of the anchor
            'feed': feed_infos[0],
            'feeds': feed_infos,
            'details': details,
            'waypoints': _waypoints_payload(
                distances, _waypoint_locales(set(distances)))
        }
