import logging

from c2corg_api.views.markdown import cook
from c2corg_api.views.resource import resource, view

log = logging.getLogger(__name__)


def validate_markdowns(request, **kwargs):
    """Check that the body is a JSON object (of markdowns)."""
    # an invalid JSON body raises here: the catch-all error view answers it
    if not isinstance(request.json_body, dict):
        request.errors.add('body', '', 'Should be a JSON object')


@resource(path='/cooker')
class CookerRest:
    def __init__(self, request, **kwargs):
        self.request = request

    @view(validators=[validate_markdowns])
    def post(self):
        """Thi service is a stateless service that returns HTML values.

        * Input and output are dictionaries
        * keys are keep unmodified
        * values are parsed from markdown to HTML, only if key is not in
          c2corg_api.views.markdown.NOT_MARKDOWN_PROPERTY
        """
        return cook(self.request.json)
