from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.search import search, SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX
from c2corg_api.views import cors_policy
from c2corg_api.views.area import area_documents_config
from c2corg_api.views.article import article_documents_config
from c2corg_api.views.book import book_documents_config
from c2corg_api.views.image import image_documents_config
from c2corg_api.views.outing import outing_documents_config
from c2corg_api.views.route import route_documents_config
from c2corg_api.views.topo_map import topo_map_documents_config
from c2corg_api.views.user_profile import user_profile_documents_config
from c2corg_api.views.validation import validate_pagination, \
    validate_preferred_lang_param
from c2corg_api.views.waypoint import waypoint_documents_config
from cornice.resource import resource, view


@resource(path='/search', cors_policy=cors_policy)
class SearchRest(object):
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def get(self):
        """Search for a query word (simple search).

        Request:
            `GET` `/search?q=...[&lang=...][&limit=...][&t=...]`

        Parameters:
            `q=...`
            The search word.

            `lang=...` (optional)
            When set only the given locale will be included (if available).
            Otherwise all locales will be returned.

            `limit=...` (optional)
            How many results should be returned per document type
            (default: 10). The maximum is 50.

            `t=...` (optional)
            Which document types should be included in the search. If not
            given, all document types are returned. Example: `...&t=w,r`
            searches only for waypoints and routes.
        """
        search_term = self.request.params.get('q')
        lang = self.request.validated.get('lang')
        limit = self.request.validated.get('limit')
        limit = min(
            SEARCH_LIMIT_DEFAULT if limit is None else limit,
            SEARCH_LIMIT_MAX)
        types_to_include = self._parse_types_to_include(
            self.request.params.get('t'))

        search_types = []
        if self._include_type(WAYPOINT_TYPE, types_to_include):
            search_types.append(('waypoints', waypoint_documents_config))

        if self._include_type(ROUTE_TYPE, types_to_include):
            search_types.append(('routes', route_documents_config))

        if self._include_type(OUTING_TYPE, types_to_include):
            search_types.append(('outings', outing_documents_config))

        if self._include_type(AREA_TYPE, types_to_include):
            search_types.append(('areas', area_documents_config))

        if self._include_type(ARTICLE_TYPE, types_to_include):
            search_types.append(('articles', article_documents_config))

        if self._include_type(BOOK_TYPE, types_to_include):
            search_types.append(('books', book_documents_config))

        if self._include_type(MAP_TYPE, types_to_include):
            search_types.append(('maps', topo_map_documents_config))

        if self._include_type(IMAGE_TYPE, types_to_include):
            search_types.append(('images', image_documents_config))

        if self._include_type(USERPROFILE_TYPE, types_to_include) and \
                self.request.has_permission('authenticated'):
            search_types.append(('users', user_profile_documents_config))

        return search.search_for_types(search_types, search_term, limit, lang)

    def _parse_types_to_include(self, types_in):
        if not types_in:
            return None
        return types_in.split(',')

    def _include_type(self, doc_type, types_to_include):
        if not types_to_include:
            return True
        else:
            return doc_type in types_to_include
