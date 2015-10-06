from cornice.resource import resource, view

from c2corg_api.models.route import Route, schema_route, schema_update_route
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import validate_id


@resource(collection_path='/routes', path='/routes/{id}')
class RouteRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(Route, schema_route)

    @view(validators=validate_id)
    def get(self):
        return self._get(Route, schema_route)

    @view(schema=schema_route)
    def collection_post(self):
        return self._collection_post(Route, schema_route)

    @view(schema=schema_update_route, validators=validate_id)
    def put(self):
        return self._put(Route, schema_route)
