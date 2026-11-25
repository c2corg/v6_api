import re

from sqlalchemy import inspect, select

from c2corg_api.markdown import get_text_references, parse_code
from c2corg_api.markdown.img import (
    IMG_ID_RE,
    make_image_size_resolver,
    make_image_url_resolver,
)
from c2corg_api.models import DBSession
from c2corg_api.models.document import Document
from c2corg_api.models.document_link import LINK_TYPE_NAMES, DocumentLink
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

# loose pattern of the ids of the [[type/id|label]] links, before parsing
WIKILINK_ID_RE = re.compile(r'\[\[[a-z]+/(\d+)')

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
    link_type_resolver = _get_link_type_resolver(data)

    result = {}
    for key in data:
        if key not in NOT_MARKDOWN_PROPERTY and data[key]:
            result[key] = parse_code(
                data[key], image_url_resolver, image_size_resolver, link_type_resolver
            )
        else:
            result[key] = data[key]

    return result


def _get_link_type_resolver(data):
    """Resolve the types of the documents of the [[type/id|label]] links."""
    # in one query: a link with a wrong or old type (v5 "summits", "route"...)
    # leads to the document of its id all the same; it is listed as broken to
    # be corrected (see views.document_links). Unknown ids keep their type.
    ids = set()
    for key, value in data.items():
        if key not in NOT_MARKDOWN_PROPERTY and isinstance(value, str):
            ids.update(int(i) for i in WIKILINK_ID_RE.findall(value))
    ids = {i for i in ids if i <= _MAX_DOCUMENT_ID}
    if not ids:
        return None
    types = dict(
        DBSession.execute(
            select(Document.document_id, Document.type).where(
                Document.document_id.in_(ids)
            )
        ).all()
    )
    names = {i: LINK_TYPE_NAMES.get(t) for i, t in types.items()}
    return names.get


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
    return get_locale_references(locale)[0]


def get_locale_references(locale):
    """Return the images shown and the documents linked by a locale (model)."""
    # the texts cook() cooks: the string columns of the locale, but the ones
    # that are not markdown and the polymorphic type. The links are
    # (type as written, id, written as a URL), see get_text_references.
    image_ids = set()
    links = {}
    for attribute in inspect(locale).mapper.column_attrs:
        key = attribute.key
        value = getattr(locale, key)
        if key in NOT_MARKDOWN_PROPERTY or key == 'type':
            continue
        # no image tag nor link: skip the parser, the costly part
        if isinstance(value, str) and (
            '[img=' in value or '[[' in value or 'camptocamp.org' in value
        ):
            ids, text_links = get_text_references(value)
            image_ids.update(ids)
            for target_type, target_id, is_url in text_links:
                # a link written both ways counts as [[type/id|label]]
                link = (target_id, target_type)
                links[link] = links.get(link, True) and is_url
    # larger ids can't be documents, cook() leaves them out too
    return (
        {i for i in image_ids if i <= _MAX_DOCUMENT_ID},
        {link: is_url for link, is_url in links.items() if link[0] <= _MAX_DOCUMENT_ID},
    )


def update_text_references(locales):
    """Store the images shown and the documents linked by these locales."""
    locales = list(locales)
    if not locales:
        return
    ids = [locale.id for locale in locales]
    embeds = ImageEmbed.__table__
    links = DocumentLink.__table__
    DBSession.execute(embeds.delete().where(embeds.c.document_locale_id.in_(ids)))
    DBSession.execute(links.delete().where(links.c.document_locale_id.in_(ids)))
    embed_rows = []
    link_rows = []
    for locale in locales:
        image_ids, locale_links = get_locale_references(locale)
        common = {
            'document_locale_id': locale.id,
            'document_id': locale.document_id,
            'lang': locale.lang,
        }
        embed_rows += [{**common, 'image_id': i} for i in sorted(image_ids)]
        link_rows += [
            {
                **common,
                'target_id': target_id,
                'target_type': target_type[:20],
                'is_url': is_url,
            }
            for (target_id, target_type), is_url in sorted(locale_links.items())
        ]
    if embed_rows:
        DBSession.execute(embeds.insert(), embed_rows)
    if link_rows:
        DBSession.execute(links.insert(), link_rows)
