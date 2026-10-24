from cornice.resource import resource, view

from c2corg_api.models import DBSession
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.views import cors_policy
from c2corg_api.views.transport import (
    CACHE_CONTROL,
    get_stops_in_bbox,
    validate_bbox_param,
)
from c2corg_api.views.validation import (
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)

validate_stoparea_create = ['navitia_id', 'stoparea_name', 'line', 'operator', 'geom']

validate_stoparea_update = validate_stoparea_create


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
        """
        Get a list of stopareas.

        `bbox=xmin,ymin,xmax,ymax` (optional)
        A search bbox in EPSG:3857. When set, the result is not paginated
        and contains one entry per stop (instead of one per stop and line):
        the GTFS stops (`kind: gtfs`, light: the timetables are read with
        `/transport-stops/{id}`) and the Navitia stops that are not matched
        with a GTFS stop (`kind: navitia`, with their `lines` and the
        `waypoints` they are associated with).

        `all=1` (optional, with `bbox`)
        Includes the GTFS stops that are not linked to a waypoint
        (otherwise only the linked ones are returned).
        """
        bbox = self.request.validated.get('bbox')
        if bbox:
            documents = get_stops_in_bbox(bbox, self.request.GET.get('all') == '1')
            self.request.response.headers['Cache-Control'] = CACHE_CONTROL
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
