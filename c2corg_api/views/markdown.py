from sqlalchemy import inspect

from c2corg_api.markdown import get_embedded_image_ids, parse_code
from c2corg_api.markdown.img import (
    IMG_ID_RE,
    make_image_size_resolver,
    make_image_url_resolver,
)
from c2corg_api.models import DBSession
from c2corg_api.models.image import get_shown_images
from c2corg_api.models.image_embed import ImageEmbed

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
    image_url_resolver, image_size_resolver = _get_image_resolvers(data)

    result = {}
    for key in data:
        if key not in NOT_MARKDOWN_PROPERTY and data[key]:
            result[key] = parse_code(data[key], image_url_resolver, image_size_resolver)
        else:
            result[key] = data[key]

    return result


def _get_image_resolvers(data):
    """Resolve the images embedded in `data` in one query: URL and size."""
    # this lets the cooked HTML link them directly on the media server, and
    # give the size of their original. Unknown images are left out: their
    # <img> only get the c2c:url-proxy attribute. Merged images get the URL
    # and size of the image they redirect to.
    image_ids = set()
    for key, value in data.items():
        if key not in NOT_MARKDOWN_PROPERTY and isinstance(value, str):
            image_ids.update(int(i) for i in IMG_ID_RE.findall(value))
    image_ids = {i for i in image_ids if i <= _MAX_DOCUMENT_ID}
    if not image_ids:
        return None, None

    images = get_shown_images(image_ids)
    sizes = {i: (width, height) for i, (_, width, height) in images.items()}
    filenames = {i: filename for i, (filename, _, _) in images.items()}
    url_resolver = (
        make_image_url_resolver(_image_url, filenames) if _image_url else None
    )
    return url_resolver, make_image_size_resolver(sizes)


def get_locale_image_ids(locale):
    """Return the ids of the images shown in the texts of a locale (model)."""
    # the texts cook() cooks: the string columns of the locale, but the ones
    # that are not markdown and the polymorphic type
    image_ids = set()
    for attribute in inspect(locale).mapper.column_attrs:
        key = attribute.key
        value = getattr(locale, key)
        if key in NOT_MARKDOWN_PROPERTY or key == 'type':
            continue
        # no "[img=", no image: skip the parser, the costly part
        if isinstance(value, str) and '[img=' in value:
            image_ids.update(get_embedded_image_ids(value))
    # larger ids can't be documents, cook() leaves them out too
    return {i for i in image_ids if i <= _MAX_DOCUMENT_ID}


def update_image_embeds(locales):
    """Store the images embedded in the texts of these locales (flushed)."""
    locales = list(locales)
    if not locales:
        return
    table = ImageEmbed.__table__
    DBSession.execute(
        table.delete().where(
            table.c.document_locale_id.in_([locale.id for locale in locales])
        )
    )
    rows = [
        {
            'document_locale_id': locale.id,
            'image_id': image_id,
            'document_id': locale.document_id,
            'lang': locale.lang,
        }
        for locale in locales
        for image_id in sorted(get_locale_image_ids(locale))
    ]
    if rows:
        DBSession.execute(table.insert(), rows)
