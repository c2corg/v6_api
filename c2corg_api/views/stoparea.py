from c2corg_api.models import DBSession
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.views.resource import view
from c2corg_api.views.validation import (
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)

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


@view(
    validators=[
        validate_pagination,
        validate_preferred_lang_param,
        validate_page_params,
    ]
)
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


@view(validators=[validate_id, validate_lang_param])
def read_stoparea(request):
    """Get a single stoparea."""
    stoparea_id = request.matchdict['id']
    stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

    if not stoparea:
        request.response.status = 404
        return {'error': 'Stoparea not found'}

    return stoparea.to_dict()


@view(validators=[validate_id, validate_lang])
def read_stoparea_info(request):
    stoparea_id = request.matchdict['id']
    stoparea = DBSession.query(Stoparea).filter_by(stoparea_id=stoparea_id).first()

    if not stoparea:
        request.response.status = 404
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
