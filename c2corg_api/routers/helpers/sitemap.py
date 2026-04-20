"""
Sitemap (JSON) helpers.

Extracted from ``c2corg_api.views.sitemap``.
"""

from datetime import date
from math import ceil

from fastapi import HTTPException
from sqlalchemy import func

from c2corg_api import caching
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE

PAGES_PER_SITEMAP = 45000


def get_cache_key(doc_type=None, i=None):
    if doc_type:
        return '{}-{}-{}-{}'.format(
            doc_type, i, date.today().isoformat(), caching.CACHE_VERSION
        )
    else:
        return '{}-{}'.format(date.today().isoformat(), caching.CACHE_VERSION)


def get_sitemap_index():
    document_locales_per_type = (
        resolve_db(None)
        .query(Document.type, func.count().label('count'))
        .join(DocumentLocale, Document.document_id == DocumentLocale.document_id)
        .filter(Document.type != USERPROFILE_TYPE)
        .group_by(Document.type)
        .all()
    )

    sitemaps = []
    for doc_type, count in document_locales_per_type:
        num_sitemaps = ceil(count / PAGES_PER_SITEMAP)
        sitemaps.extend(
            {'url': '/sitemaps/{}/{}'.format(doc_type, i), 'doc_type': doc_type, 'i': i}
            for i in range(num_sitemaps)
        )

    return {'sitemaps': sitemaps}


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
        resolve_db(None)
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

    return {'pages': [_format_page(locale, is_route) for locale in document_locales]}


def _format_page(document_locale, is_route):
    if not is_route:
        doc_id, lang, title, last_updated = document_locale
    else:
        doc_id, lang, title, last_updated, title_prefix = document_locale

    page = {
        'document_id': doc_id,
        'lang': lang,
        'title': title,
        'lastmod': last_updated.isoformat(),
    }

    if is_route:
        page['title_prefix'] = title_prefix

    return page
