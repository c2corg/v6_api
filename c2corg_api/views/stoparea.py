import math

from cornice.resource import resource, view
from sqlalchemy import func

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.views import cors_policy
from c2corg_api.views.validation import (
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)

validate_stoparea_create = ['navitia_id', 'stoparea_name', 'line', 'operator', 'geom']

validate_stoparea_update = validate_stoparea_create

# safety net: a stop is stored once per line, a wide bbox could return a lot
MAX_STOPAREAS_BY_BBOX = 5000

# The map asks for extents aligned on a fixed grid, so that the same urls come
# back: the browsers may keep the answers. The stops only change when the
# imports are run.
BBOX_CACHE_CONTROL = 'public, max-age=3600'


def validate_bbox_param(request, **kwargs):
    """Check the optional `bbox` parameter (EPSG:3857).

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

    if (
        len(values) != 4
        or not all(math.isfinite(v) for v in values)
        or values[0] >= values[2]
        or values[1] >= values[3]
    ):
        request.errors.add(
            'querystring',
            'bbox',
            'invalid bbox, expected xmin,ymin,xmax,ymax (EPSG:3857)',
        )
        return

    request.validated['bbox'] = values


def _get_stopareas_in_bbox(bbox):
    """Return the stops located in the given bbox, one entry per stop.

    Returns the stops located in the given bbox (EPSG:3857), one entry per
    stop (a stop is stored once per line in the database), with its lines and
    the waypoints it has been associated with (nearest first).
    """
    envelope = func.ST_MakeEnvelope(*bbox, 3857)
    stopareas = (
        DBSession.query(Stoparea)
        .filter(func.ST_Intersects(Stoparea.geom, envelope))
        .order_by(Stoparea.stoparea_id)
        .limit(MAX_STOPAREAS_BY_BBOX)
        .all()
    )

    if not stopareas:
        return []

    distances = {}  # navitia_id -> {waypoint_id: distance}
    navitia_id_by_stoparea = {s.stoparea_id: s.navitia_id for s in stopareas}
    links = (
        DBSession.query(
            WaypointStoparea.stoparea_id,
            WaypointStoparea.waypoint_id,
            WaypointStoparea.distance,
        )
        .filter(WaypointStoparea.stoparea_id.in_(navitia_id_by_stoparea.keys()))
        .all()
    )
    for stoparea_id, waypoint_id, distance in links:
        by_waypoint = distances.setdefault(navitia_id_by_stoparea[stoparea_id], {})
        by_waypoint[waypoint_id] = min(distance, by_waypoint.get(waypoint_id, distance))

    waypoint_ids = {wid for by_wp in distances.values() for wid in by_wp}
    locales = {}  # waypoint_id -> [{lang, title}]
    if waypoint_ids:
        for document_id, lang, title in DBSession.query(
            DocumentLocale.document_id, DocumentLocale.lang, DocumentLocale.title
        ).filter(DocumentLocale.document_id.in_(waypoint_ids)):
            locales.setdefault(document_id, []).append({'lang': lang, 'title': title})

    stops = {}  # navitia_id -> stop, insertion ordered
    for stoparea in stopareas:
        data = stoparea.to_dict()
        stop = stops.get(stoparea.navitia_id)
        if stop is None:
            stop = stops[stoparea.navitia_id] = {
                'navitia_id': stoparea.navitia_id,
                'stoparea_name': stoparea.stoparea_name,
                'coordinates': data['coordinates'],
                'lines': [],
                'waypoints': [
                    {
                        'document_id': waypoint_id,
                        'distance': round(distance, 2),
                        'locales': locales.get(waypoint_id, []),
                    }
                    for waypoint_id, distance in sorted(
                        distances.get(stoparea.navitia_id, {}).items(),
                        key=lambda item: item[1],
                    )
                ],
            }
        stop['lines'].append(
            {
                'id': stoparea.stoparea_id,
                'line': stoparea.line,
                'operator': stoparea.operator,
            }
        )

    return list(stops.values())


@resource(collection_path='/stopareas', path='/stopareas/{id}', cors_policy=cors_policy)
class StopareaRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(
        validators=[
            validate_pagination,
            validate_preferred_lang_param,
            validate_bbox_param,
        ]
    )
    def collection_get(self):
        """Get a list of stopareas.

        `bbox=xmin,ymin,xmax,ymax` (optional)
        A search bbox in EPSG:3857. When set, the result is not paginated
        and contains one entry per stop (instead of one per stop and line),
        with its `lines` and the `waypoints` it is associated with.
        """
        bbox = self.request.validated.get('bbox')
        if bbox:
            documents = _get_stopareas_in_bbox(bbox)
            self.request.response.headers['Cache-Control'] = BBOX_CACHE_CONTROL
            return {'documents': documents, 'total_results': len(documents)}

        page_id = self.request.GET.get('page_id', 1)
        nb_items = self.request.GET.get('nb_items', 30)

        query = DBSession.query(Stoparea)
        total_results = query.count()

        stopareas = query.offset((page_id - 1) * nb_items).limit(nb_items).all()

        return {
            'documents': [stoparea.to_dict() for stoparea in stopareas],
            'total_results': total_results,
        }

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """Get a single stoparea."""
        stoparea_id = self.request.matchdict['id']
        stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

        if not stoparea:
            self.request.response.status = 404
            return {'error': 'Stoparea not found'}

        return stoparea.to_dict()


@resource(path='/stopareas/{id}/{lang}/info', cors_policy=cors_policy)
class StopareaInfoRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_id, validate_lang])
    def get(self):
        stoparea_id = self.request.matchdict['id']
        stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

        if not stoparea:
            self.request.response.status = 404
            return {'error': 'Stoparea not found'}

        return {
            'stoparea_id': stoparea.stoparea_id,
            'attributes': {
                'navitia_id': stoparea.navitia_id,
                'stoparea_name': stoparea.stoparea_name,
                'line': stoparea.line,
                'operator': stoparea.operator,
                'geom': str(stoparea.geom),
            },
        }
