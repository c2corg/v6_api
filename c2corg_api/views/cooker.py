import logging

from c2corg_api.views import cors_policy
from c2corg_api.views.markdown import cook
from cornice.resource import resource, view

log = logging.getLogger(__name__)


@resource(path='/cooker', cors_policy=cors_policy)
class CookerRest(object):
    @view()
    def post(self):
        return cook(self.request.json)
