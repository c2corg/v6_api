import functools
import logging

from c2corg_api import DBSession, caching
from c2corg_api.caching import cache_sitemap
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.views import cors_policy, etag_cache
from c2corg_api.views.validation import create_int_validator, \
    validate_document_type
from c2corg_api.caching import get_or_create
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.sql.functions import func
from math import ceil
from datetime import date

log = logging.getLogger(__name__)

# Search engines accept not more than 50000 urls per sitemap,
# and the sitemap files may not exceed 10 MB. With 50000 urls the sitemaps
# are not bigger than 9MB, but to be safe we are using 45000 urls per sitemap.
# see http://www.sitemaps.org/protocol.html
PAGES_PER_SITEMAP = 45000


validate_page = create_int_validator('i')


@resource(
    collection_path='/sitemaps', path='/sitemaps/{doc_type}/{i}',
    cors_policy=cors_policy)
class SitemapRest(object):

    def __init__(self, request):
        self.request = request

    @view()
    def collection_get(self):
        """ Returns the information needed to generate a sitemap index file.
        See: http://www.sitemaps.org/protocol.html

        The response consists of a list of URLs to request the information
        needed to generate the sitemap linked from the sitemap index.

        E.g.

            {
                "sitemaps": [
                    "/sitemaps/w/0",
                    "/sitemaps/a/0",
                    "/sitemaps/i/0",
                    "/sitemaps/i/1",
                    "/sitemaps/i/2",
                    "/sitemaps/i/3",
                    "/sitemaps/i/4",
                    "/sitemaps/i/5",
                    ...
                ]
            }
        """
        cache_key = _get_cache_key()
        etag_cache(self.request, cache_key)

        return get_or_create(
            cache_sitemap, cache_key, _get_sitemap_index)

    @view(validators=[validate_page, validate_document_type])
    def get(self):
        """ Returns the information needed to generate a sitemap for a given
        type and sitemap page number.
        """
        doc_type = self.request.validated['doc_type']
        i = self.request.validated['i']

        cache_key = _get_cache_key(doc_type, i)
        etag_cache(self.request, cache_key)

        return get_or_create(
            cache_sitemap,
            cache_key,
            functools.partial(_get_sitemap, doc_type, i))


def _get_cache_key(doc_type=None, i=None):
    if doc_type:
        return '{}-{}-{}-{}'.format(
            doc_type, i, date.today().isoformat(), caching.CACHE_VERSION)
    else:
        return '{}-{}'.format(
            date.today().isoformat(), caching.CACHE_VERSION)


def _get_sitemap_index():
    document_locales_per_type = DBSession. \
        query(Document.type, func.count().label('count')). \
        join(
            DocumentLocale,
            Document.document_id == DocumentLocale.document_id). \
        filter(Document.type != USERPROFILE_TYPE). \
        group_by(Document.type). \
        all()

    sitemaps = []
    for doc_type, count in document_locales_per_type:
        num_sitemaps = ceil(count / PAGES_PER_SITEMAP)
        sitemaps_for_type = [
            {
                'url': '/sitemaps/{}/{}'.format(doc_type, i),
                'doc_type': doc_type,
                'i': i
            }
            for i in range(0, num_sitemaps)
            ]
        sitemaps.extend(sitemaps_for_type)

    return {
        'sitemaps': sitemaps
    }


def _get_sitemap(doc_type, i):
    fields = [
        Document.document_id, DocumentLocale.lang, DocumentLocale.title,
        CacheVersion.last_updated
    ]

    # include `title_prefix` for routes
    is_route = doc_type == ROUTE_TYPE
    if is_route:
        fields.append(RouteLocale.title_prefix)

    base_query = DBSession. \
        query(*fields). \
        select_from(Document). \
        join(DocumentLocale,
             Document.document_id == DocumentLocale.document_id)

    if is_route:
        # joining on `RouteLocale.__table_` instead of `RouteLocale` to
        # avoid that SQLAlchemy create an additional join on DocumentLocale
        base_query = base_query. \
            join(RouteLocale.__table__,
                 DocumentLocale.id == RouteLocale.id)

    base_query = base_query. \
        join(CacheVersion,
             Document.document_id == CacheVersion.document_id). \
        filter(Document.redirects_to.is_(None)). \
        filter(Document.type == doc_type). \
        order_by(Document.document_id, DocumentLocale.lang). \
        limit(PAGES_PER_SITEMAP). \
        offset(PAGES_PER_SITEMAP * i)

    document_locales = base_query.all()

    if not document_locales:
        raise HTTPNotFound()

    return {
        'pages': [
            _format_page(locale, is_route)
            for locale in document_locales
        ]
    }


def _format_page(document_locale, is_route):
    if not is_route:
        doc_id, lang, title, last_updated = document_locale
    else:
        doc_id, lang, title, last_updated, title_prefix = document_locale

    page = {
        'document_id': doc_id,
        'lang': lang,
        'title': title,
        'lastmod': last_updated.isoformat()
    }

    if is_route:
        page['title_prefix'] = title_prefix

    return page
