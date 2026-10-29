from c2corg_api.markdown import parse_code
from c2corg_api.markdown.img import IMG_ID_RE, make_image_url_resolver
from c2corg_api.models.image import get_image_filenames

# locale properties that must not be cooked by markdown parser
NOT_MARKDOWN_PROPERTY = {
    'lang',
    'version',
    'title',
    'slope',
    'conditions_levels',
    'topic_id',
    'participants',
}

# document ids are postgres integers, larger values can't be queried
_MAX_DOCUMENT_ID = 2**31 - 1

# the URL of the image server (setting image_url), set by the application
_image_url = None


def configure_image_url(settings):
    """Link the images of the cooked HTML to the image server, if configured."""
    global _image_url
    _image_url = settings.get('image_url') or None


def cook(data):
    image_url_resolver = _get_image_url_resolver(data)

    result = {}
    for key in data:
        if key not in NOT_MARKDOWN_PROPERTY and data[key]:
            result[key] = parse_code(data[key], image_url_resolver)
        else:
            result[key] = data[key]

    return result


def _get_image_url_resolver(data):
    """Resolve the filenames of all images embedded in `data` in one query."""
    # this lets the cooked HTML link them directly on the media server.
    # Unknown images are left out: their <img> only get the c2c:url-proxy
    # attribute. Merged images get the URL of the image they redirect to.
    image_ids = set()
    for key, value in data.items():
        if key not in NOT_MARKDOWN_PROPERTY and isinstance(value, str):
            image_ids.update(int(i) for i in IMG_ID_RE.findall(value))
    image_ids = {i for i in image_ids if i <= _MAX_DOCUMENT_ID}
    if not image_ids:
        return None

    if not _image_url:
        return None

    return make_image_url_resolver(_image_url, get_image_filenames(image_ids))
