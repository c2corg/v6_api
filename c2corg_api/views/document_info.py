from c2corg_api.caching import cache_document_info
from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import DocumentLocale, Document, \
    get_available_langs
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.views import etag_cache, \
    set_best_locale
from c2corg_api.views.document_listings import add_load_for_profiles
from c2corg_api.caching import get_or_create
from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.orm import contains_eager, load_only, joinedload
from sqlalchemy.orm.util import with_polymorphic


class DocumentInfoRest(object):
    """ Base class for all views that return a basic/info version for a
    document, that only contains the document_id and title/title_prefix
    of the requested locale.
    This view is used by the UI to generate URL slugs.

    If the locale is not available in the requested lang, a locale in the
    "best" lang is returned.
    If the requested document is redirected, the document id and available
    languages of the redirection document is returned.
    """

    def __init__(self, request):
        self.request = request

    def _get_document_info(self, document_config):
        document_id = self.request.validated['id']
        lang = self.request.validated['lang']

        def create_response():
            return self._load_document_info(
                document_id,
                lang,
                document_config.clazz)

        cache_key = get_cache_key(
            document_id,
            lang,
            document_type=document_config.document_type)

        if not cache_key:
            raise HTTPNotFound(
                'no version for document {0}'.format(document_id))
        else:
            etag_cache(self.request, cache_key)

            return get_or_create(
                cache_document_info, cache_key, create_response)

    def _load_document_info(self, document_id, lang, clazz):
        is_route = clazz == Route
        locales_type = with_polymorphic(DocumentLocale, RouteLocale) \
            if is_route else DocumentLocale
        locales_attr = getattr(clazz, 'locales')
        locales_type_eager = locales_attr.of_type(RouteLocale) \
            if is_route else locales_attr
        locales_load_only = [
            DocumentLocale.lang, DocumentLocale.title, DocumentLocale.version]
        if is_route:
            locales_load_only.append(RouteLocale.title_prefix)

        document_query = DBSession. \
            query(clazz). \
            options(load_only(
                Document.document_id, Document.version,
                Document.redirects_to, Document.protected)). \
            join(locales_type). \
            filter(getattr(clazz, 'document_id') == document_id). \
            filter(DocumentLocale.lang == lang). \
            options(contains_eager(locales_type_eager, alias=locales_type).
                    load_only(*locales_load_only))
        document_query = add_load_for_profiles(document_query, clazz)
        document = document_query.first()

        if not document:
            # the requested locale might not be available, try to get the
            # document with all locales and set the "best"
            document_query = DBSession. \
                query(clazz). \
                options(load_only(
                    Document.document_id, Document.version,
                    Document.redirects_to, Document.protected)). \
                filter(getattr(clazz, 'document_id') == document_id). \
                options(joinedload(locales_type_eager).
                        load_only(*locales_load_only))

            document_query = add_load_for_profiles(document_query, clazz)
            document = document_query.first()

            if not document:
                raise HTTPNotFound('document not found')

            if document.document_id:
                # TODO: find a better way than this workaround which calls
                # `document_id` before `set_best_locale` expunge the object
                # leading in: sqlalchemy.orm.exc.DetachedInstanceError:
                # Parent instance <Article at ...> is not bound to a Session;
                # deferred load operation of attribute 'document_id' cannot proceed
                pass
            set_best_locale([document], lang)

        if document.redirects_to:
            return {
                'redirects_to': document.redirects_to,
                'available_langs': get_available_langs(
                    document.redirects_to)
            }

        assert len(document.locales) == 1
        locale = document.locales[0]

        return {
            'document_id': document.document_id,
            'locales': [{
                'lang': locale.lang,
                'title':
                    locale.title
                    if clazz != UserProfile else document.name,
                'title_prefix': locale.title_prefix if is_route else None
            }]
        }
