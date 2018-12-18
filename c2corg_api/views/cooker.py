import logging

from c2corg_api.views import cors_policy
from c2corg_api.views.markdown import cook
from cornice.resource import resource, view

log = logging.getLogger(__name__)


@resource(path='/cooker', cors_policy=cors_policy)
class CookerRest(object):

    def __init__(self, request):
        self.request = request

    @view()
    def post(self):
        """
        This service is a stateless service that returns HTML values.

        * Input and output are dictionaries
        * keys are keep unmodified
        * values are parsed from markdown to HTML, only if key is not in
          c2corg_api.views.markdown.NOT_MARKDOWN_PROPERTY
        """
        return cook(self.request.json)
