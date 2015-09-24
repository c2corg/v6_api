from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from api.models.route import Route, schema_route
from api.models import DBSession
from api.views.document import DocumentRest
from . import validate_id, to_json_dict


@resource(collection_path='/routes', path='/routes/{id}')
class RouteRest(DocumentRest):

    def collection_get(self):
        routes = DBSession. \
            query(Route). \
            options(joinedload(Route.locales)). \
            limit(30)

        return [to_json_dict(wp, schema_route) for wp in routes]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']

        route = DBSession. \
            query(Route). \
            filter(Route.document_id == id). \
            options(joinedload(Route.locales)). \
            first()

        return to_json_dict(route, schema_route)

    @view(schema=schema_route)
    def collection_post(self):
        route = schema_route.objectify(self.request.validated)

        DBSession.add(route)
        DBSession.flush()

        self._create_new_version(route)

        return to_json_dict(route, schema_route)
