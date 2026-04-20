"""
Sitemap XML helpers.

Extracted from ``c2corg_api.views.sitemap_xml``.
"""

from c2corg_api.models import DBSession
from datetime import date, datetime, timezone
from math import ceil

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy import func

from c2corg_api import caching
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE

PAGES_PER_SITEMAP = 45000

UI_ENTRY_POINTS = {
    'a': 'areas',
    'b': 'books',
    'c': 'articles',
    'i': 'images',
    'm': 'maps',
    'o': 'outings',
    'r': 'routes',
    'w': 'waypoints',
    'x': 'xreports',
}


def get_cache_key(doc_type=None, i=None):
    if doc_type:
        return '{}-{}-{}-{}'.format(
            doc_type, i, date.today().isoformat(), caching.CACHE_VERSION
        )
    else:
        return '{}-{}'.format(date.today().isoformat(), caching.CACHE_VERSION)


def get_sitemap_index():
    document_locales_per_type = (
        DBSession
        .query(Document.type, func.count().label('count'))
        .join(DocumentLocale, Document.document_id == DocumentLocale.document_id)
        .filter(Document.type != USERPROFILE_TYPE)
        .group_by(Document.type)
        .all()
    )

    sitemaps = []
    now = datetime.now(timezone.utc)
    lastmod = now.isoformat()

    template = (
        '<sitemap>\n'
        '    <loc>https://api.camptocamp.org'
        '/sitemaps.xml/{doc_type}/{i}.xml</loc>\n'
        '    <lastmod>{lastmod}</lastmod>\n'
        '</sitemap>'
    )

    for doc_type, count in document_locales_per_type:
        num_sitemaps = ceil(count / PAGES_PER_SITEMAP)
        sitemaps.extend(
            template.format(doc_type=doc_type, i=i, lastmod=lastmod)
            for i in range(num_sitemaps)
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '    <sitemapindex xmlns='
        '"http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '    {}\n'
        '    </sitemapindex>'
    ).format('\n'.join(sitemaps))


def get_sitemap(doc_type, i):
    fields = [
        Document.document_id,
        DocumentLocale.lang,
        DocumentLocale.title,
        CacheVersion.last_updated,
    ]

    is_route = doc_type == ROUTE_TYPE
    if is_route:
        fields.append(RouteLocale.title_prefix)

    base_query = (
        DBSession
        .query(*fields)
        .select_from(Document)
        .join(DocumentLocale, Document.document_id == DocumentLocale.document_id)
    )

    if is_route:
        base_query = base_query.join(
            RouteLocale.__table__, DocumentLocale.id == RouteLocale.id
        )

    base_query = (
        base_query.join(CacheVersion, Document.document_id == CacheVersion.document_id)
        .filter(Document.redirects_to.is_(None))
        .filter(Document.type == doc_type)
        .order_by(Document.document_id, DocumentLocale.lang)
        .limit(PAGES_PER_SITEMAP)
        .offset(PAGES_PER_SITEMAP * i)
    )

    document_locales = base_query.all()

    if not document_locales:
        raise HTTPException(status_code=404)

    ui_entry_point = UI_ENTRY_POINTS[doc_type]

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '    <urlset xmlns='
        '"http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '    {}\n'
        '    </urlset>'
    ).format(
        '\n'.join(_format_page(ui_entry_point, *locale) for locale in document_locales)
    )


def _format_page(ui_entry_point, doc_id, lang, title, last_updated, title_prefix=None):
    page = {
        'document_id': doc_id,
        'lang': lang,
        'lastmod': last_updated.isoformat(),
        'ui_entry_point': ui_entry_point,
    }

    if title_prefix:
        page['title'] = slugify('{} {}'.format(title_prefix, title))
    else:
        page['title'] = slugify(title)

    return (
        '<url>\n'
        '<loc>https://www.camptocamp.org'
        '/{ui_entry_point}/{document_id}/{lang}/{title}</loc>\n'
        '<lastmod>{lastmod}</lastmod>\n'
        '<changefreq>weekly</changefreq>\n'
        '</url>'
    ).format(**page)
