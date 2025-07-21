
from c2corg_api.models import DBSession
from cornice.resource import resource, view

from c2corg_api.models.stoparea import (Stoparea)

from c2corg_api.views import cors_policy
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_lang_param, \
    validate_preferred_lang_param

validate_stoparea_create = [
    'navitia_id', 'stoparea_name', 'line', 'operator', 'geom'
]

validate_stoparea_update = validate_stoparea_create


@resource(collection_path='/stopareas', path='/stopareas/{id}',
          cors_policy=cors_policy)
class StopareaRest:

    def __init__(self, request):
        self.request = request

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of stopareas.
        """
        page_id = self.request.GET.get('page_id', 1)
        nb_items = self.request.GET.get('nb_items', 30)

        query = DBSession.query(Stoparea)
        total_results = query.count()

        stopareas = query.offset(
            (page_id - 1) * nb_items).limit(nb_items).all()

        return {
            'documents': [stoparea.to_dict() for stoparea in stopareas],
            'total_results': total_results
        }

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single stoparea.
        """
        stoparea_id = self.request.matchdict['id']
        stoparea = DBSession.query(Stoparea).filter_by(
            stoparea_id=stoparea_id).first()

        if not stoparea:
            self.request.response.status = 404
            return {'error': 'Stoparea not found'}

        return stoparea.to_dict()


@resource(path='/stopareas/{id}/{lang}/info', cors_policy=cors_policy)
class StopareaInfoRest:

    def __init__(self, request):
        self.request = request

    @view(validators=[validate_id, validate_lang])
    def get(self):
        stoparea_id = self.request.matchdict['id']
        stoparea = DBSession.query(Stoparea).filter_by(
            stoparea_id=stoparea_id).first()

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
                'geom': str(stoparea.geom)
            }
        }
