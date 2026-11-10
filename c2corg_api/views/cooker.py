import logging

from c2corg_api.views.markdown import cook
from c2corg_api.views.resource import write

log = logging.getLogger(__name__)


def validate_markdowns(request, **kwargs):
    """Check that the body is a JSON object (of markdowns)."""
    # an invalid JSON body raises here: the catch-all error view answers it
    if not isinstance(request.json_body, dict):
        request.errors.add('body', '', 'Should be a JSON object')


# A POST, though it changes nothing: the markdowns of a whole locale (tens of
# KB for a route description) do not fit in a URL. As a POST, it counts in
# the write quota of an authenticated user (security.rate_limiting): one per
# preview in the editor.
@write(validators=[validate_markdowns], json=False)
def cook_markdown(request):
    """Thi service is a stateless service that returns HTML values.

    * Input and output are dictionaries
    * keys are keep unmodified
    * values are parsed from markdown to HTML, only if key is not in
      c2corg_api.views.markdown.NOT_MARKDOWN_PROPERTY
    """
    return cook(request.json)
