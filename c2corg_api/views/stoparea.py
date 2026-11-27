from c2corg_api.httpexceptions import HTTPNotFound
from c2corg_api.models import DBSession
from c2corg_api.models.stoparea import Stoparea

validate_stoparea_create = ['navitia_id', 'stoparea_name', 'line', 'operator', 'geom']


def validate_page_params(request, **kwargs):
    """Check that the optional page_id and nb_items are positive integers."""
    for key in ('page_id', 'nb_items'):
        value = request.GET.get(key)
        if value is None:
            continue
        try:
            number = int(value)
            if number < 1:
                raise ValueError
            request.validated[key] = number
        except ValueError:
            request.errors.add('querystring', key, 'invalid ' + key)


validate_stoparea_update = validate_stoparea_create


def list_stopareas(request):
    """Get a list of stopareas."""
    page_id = request.validated.get('page_id', 1)
    nb_items = request.validated.get('nb_items', 30)

    query = DBSession.query(Stoparea)
    total_results = query.count()

    stopareas = query.offset((page_id - 1) * nb_items).limit(nb_items).all()

    return {
        'documents': [stoparea.to_dict() for stoparea in stopareas],
        'total_results': total_results,
    }


def read_stoparea(request):
    """Get a single stoparea."""
    stoparea_id = request.matchdict['id']
    stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

    if not stoparea:
        raise HTTPNotFound('Stoparea not found')

    return stoparea.to_dict()


def read_stoparea_info(request):
    stoparea_id = request.matchdict['id']
    stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

    if not stoparea:
        raise HTTPNotFound('Stoparea not found')

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
