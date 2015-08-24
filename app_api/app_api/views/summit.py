from cornice.resource import resource, view

from app_api.models.summit import Summit, schema_summit
from app_api.models import DBSession
from . import validate_id


@resource(collection_path='/summits', path='/summits/{id}')
class SummitRest(object):

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        return {'summits': []}

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']

        summit = DBSession. \
            query(Summit). \
            filter(Summit.id == id, Summit.is_latest_version). \
            first()

        # print(schema_summit.dictify(summit))
        # return schema_summit.serialize(schema_summit.dictify(summit))
        return schema_summit.dictify(summit)
