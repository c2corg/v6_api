import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, limit_route_fields
from c2corg_api.models.document import UpdateType, Document, DocumentLocale
from c2corg_api.models.outing import Outing, schema_association_outing
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE, \
    schema_association_route
from c2corg_api.views.outing import set_author
from c2corg_api.views.route import set_route_title_prefix
from cornice.resource import resource, view

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint,
    ArchiveWaypoint, ArchiveWaypointLocale, WAYPOINT_TYPE,
    schema_create_waypoint)

from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update,
    make_schema_adaptor, NUM_RECENT_OUTINGS)
from c2corg_api.views import cors_policy, restricted_json_view, \
    to_json_dict, set_best_locale
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations
from c2corg_common.fields_waypoint import fields_waypoint
from c2corg_common.attributes import waypoint_types
from functools import lru_cache
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy.orm.util import aliased
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import and_, union

# the number of routes that are included for waypoints
NUM_ROUTES = 30

validate_waypoint_create = make_validator_create(
    fields_waypoint, 'waypoint_type', waypoint_types)
validate_waypoint_update = make_validator_update(
    fields_waypoint, 'waypoint_type', waypoint_types)
validate_associations_create = functools.partial(
    validate_associations, WAYPOINT_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, WAYPOINT_TYPE, False)


@lru_cache(maxsize=None)
def adapt_schema_for_type(waypoint_type, field_list_type):
    """Get the schema for a waypoint type.
    `field_list_type` should be either "fields" or "listing".
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_waypoint.get(waypoint_type).get(field_list_type)
    return restrict_schema(schema_waypoint, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'waypoint_type', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'waypoint_type', 'listing')


@resource(collection_path='/waypoints', path='/waypoints/{id}',
          cors_policy=cors_policy)
class WaypointRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of documents, optionally matching search filters.
        If no search filters are given, the documents are directly queried
        from the database. If not, ElasticSearch is used to find the documents
        that match the filters.

        Request:
            `GET` `/waypoints/?[q=...][&pl=...][&offset=...][&limit=...][filters]*`  # noqa

        Parameters:
            `q=...` (optional)
            A search word.

            `bbox=xmin,ymin,xmax,ymax` (optional)
            A search bbox in EPSG:3857.

            `pl=...` (optional)
            When set only the given locale will be included (if available).
            Otherwise all locales will be returned.

            `offset=...` (optional)
            The offset to navigate through the result pages (default: 0).

            `limit=...` (optional)
            How many results should be returned per document type
            (default: 30). The maximum is 100.

        Search filters:
        An arbitrary number of search filters can be added, for example
        `/waypoints?wtyp=summit&walt=4500,5000` gets all summits with a height
        between 4500 and 5000. The available filter parameters are listed
        below.

        Generic search filters:
            `l=v1[,v2]*` (enum)
            available_locales

            `a=a1[,a2]*` (area ids)
            areas

            `qa=v1[,v2]*` (enum)
            quality

        Waypoint search filters:
        All waypoint query fields are listed in
        :class:`c2corg_api.search.mappings.waypoint_mapping.SearchWaypoint`.

        The following filter types are used:

            enums: `key=v1[,v2]*`
            One or more enum values can be given.

            boolean: `key=(1|0|true|false|True|False)`

            range: `key=[min][,max]`
            For numbers ranges can be given with a min value and a max value.

            date range: `key=from[,to]`
            Dates must be given as `yyyy-mm-dd`, e.g `2016-12-31`. If only one
            date is given, from and to are both set to that date.
        """
        return self._collection_get(
            Waypoint, schema_waypoint, WAYPOINT_TYPE,
            adapt_schema=listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single document.

        Request:
            `GET` `/waypoints/{document_id}?[l=...][&e=1]`

        Parameters:
            `l=...` (optional)
            Document locale. Get the document in the given language. If not
             provided, all document locales are returned.

            `e=1` (optional)
            Get the document for editing. Only the information needed for
            editing the document is included in the response.

        """
        return self._get(
            Waypoint, schema_waypoint,
            adapt_schema=schema_adaptor, include_maps=True,
            set_custom_associations=set_custom_associations)

    @restricted_json_view(schema=schema_create_waypoint,
                          validators=[validate_waypoint_create,
                                      validate_associations_create])
    def collection_post(self):
        """
        Create a new document.

        Request:
            `POST` `/waypoints`

        Request body:
            {
                "geometry": {
                    "geom": "{"type": "Point", "coordinates": ...}",
                    "geom_detail": "{"type": "Point", "coordinates": ...}"
                },
                ...
                "locales": [
                    {"lang": "en", "title": "...", ...}
                ],
                "associations": {
                    "routes": [
                        {"document_id": ...}
                    ]
                }
            }

        Response:
            {
                "document_id": ...
            }

        """
        return self._collection_post(schema_waypoint)

    @restricted_json_view(schema=schema_update_waypoint,
                          validators=[validate_id,
                                      validate_waypoint_update,
                                      validate_associations_update])
    def put(self):
        """
        Update a document.

        Request:
            `PUT` `/waypoints/{document_id}`

        Request body:
            {
                "message": "...",
                "document": {
                    "document_id": ...,
                    "version": ...,
                    "geometry": {
                        "version": ...,
                        "geom": "{"type": "Point", "coordinates": ...}",
                        "geom_detail": "{"type": "Point", "coordinates": ...}"
                    },
                    ...
                    "locales": [
                        {"version": ..., "lang": "en", "title": "...", ...}
                    ],
                    "associations": {
                        "routes": [
                            {"document_id": ...}
                        ]
                    }
                }
            }

            Notes:

            - The version number of the document, of each provided locale and
              of the geometry has to be given. If the versions do not match
              the current ones, `409 Conflict` is returned.
            - The geometry can be left out. In this case the geometry will not
              be changed.
            - Only the locales provided in the request will be update. If no
              locale is given, no locale will be changed.
            - Associations can be updated, by giving a list of document ids
              for the different association types. If no list is provided for
              an association type, these associations are not changed.
              For example when updating a route, association to other routes
              and waypoints can be provided. If only waypoint associations are
              given, the route associations will not be changed.
        """
        return self._put(
            Waypoint, schema_waypoint, after_update=update_linked_route_titles)


def set_custom_associations(waypoint, lang):
    set_recent_outings(waypoint, lang)
    set_linked_routes(waypoint, lang)


def set_recent_outings(waypoint, lang):
    """Set last 10 outings on routes associated to the given waypoint.
    """
    t_outing_route = aliased(Association, name='a1')
    t_route_wp = aliased(Association, name='a2')
    t_route = aliased(Document, name='r')
    with_query_waypoints = _get_select_children(waypoint)

    recent_outings = DBSession.query(Outing). \
        filter(Outing.redirects_to.is_(None)). \
        join(
            t_outing_route,
            Outing.document_id == t_outing_route.child_document_id). \
        join(
            t_route,
            and_(
                t_outing_route.parent_document_id == t_route.document_id,
                t_route.type == ROUTE_TYPE)). \
        join(
            t_route_wp,
            t_route_wp.child_document_id == t_route.document_id). \
        join(
            with_query_waypoints,
            with_query_waypoints.c.document_id == t_route_wp.parent_document_id
        ). \
        options(load_only(
            Outing.document_id, Outing.activities, Outing.date_start,
            Outing.date_end, Outing.version, Outing.protected)). \
        options(joinedload(Outing.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title,
            DocumentLocale.version)). \
        order_by(Outing.date_end.desc()). \
        limit(NUM_RECENT_OUTINGS). \
        all()

    set_author(recent_outings, None)
    if lang is not None:
        set_best_locale(recent_outings, lang)

    total = DBSession.query(Outing.document_id). \
        filter(Outing.redirects_to.is_(None)). \
        join(
            t_outing_route,
            Outing.document_id == t_outing_route.child_document_id). \
        join(
            t_route,
            and_(
                t_outing_route.parent_document_id == t_route.document_id,
                t_route.type == ROUTE_TYPE)). \
        join(
            t_route_wp,
            t_route_wp.child_document_id == t_route.document_id). \
        join(
            with_query_waypoints,
            with_query_waypoints.c.document_id == t_route_wp.parent_document_id
        ). \
        count()

    waypoint.associations['recent_outings'] = {
        'total': total,
        'outings': [
            to_json_dict(outing, schema_association_outing)
            for outing in recent_outings
        ]
    }


def set_linked_routes(waypoint, lang):
    """
    Set associated routes for the given waypoint including associated routes
    of child and grandchild waypoints.
    Note that this function returns a dict and not a list!
    """
    with_query_waypoints = _get_select_children(waypoint)

    total = DBSession.query(Route.document_id). \
        select_from(with_query_waypoints). \
        join(
            Association,
            with_query_waypoints.c.document_id ==
            Association.parent_document_id). \
        join(
            Route,
            Association.child_document_id == Route.document_id). \
        filter(Route.redirects_to.is_(None)). \
        count()

    routes = limit_route_fields(
        DBSession.query(Route).
        select_from(with_query_waypoints).
        join(
            Association,
            with_query_waypoints.c.document_id ==
            Association.parent_document_id).
        join(
            Route,
            Association.child_document_id == Route.document_id).
        filter(Route.redirects_to.is_(None)).
        order_by(Route.document_id.desc()).
        limit(NUM_ROUTES)
        ). \
        all()

    if lang is not None:
        set_best_locale(routes, lang)

    waypoint.associations['all_routes'] = {
        'total': total,
        'routes': [
            to_json_dict(route, schema_association_route)
            for route in routes
        ]
    }


def _get_select_children(waypoint):
    """
    Return a WITH query that selects the document ids of the given waypoint,
    the children and the grand-children of the waypoint.
    See also: http://docs.sqlalchemy.org/en/latest/core/selectable.html#sqlalchemy.sql.expression.GenerativeSelect.cte  # noqa
    """
    select_waypoint = DBSession. \
        query(
            literal_column(str(waypoint.document_id)).label('document_id')). \
        cte('waypoint')
    # query to get the direct child waypoints
    select_waypoint_children = DBSession. \
        query(Waypoint.document_id). \
        join(
            Association,
            and_(Association.child_document_id == Waypoint.document_id,
                 Association.parent_document_id == waypoint.document_id)). \
        cte('waypoint_children')
    # query to get the grand-child waypoints
    select_waypoint_grandchildren = DBSession. \
        query(Waypoint.document_id). \
        select_from(select_waypoint_children). \
        join(
            Association,
            Association.parent_document_id ==
            select_waypoint_children.c.document_id). \
        join(
            Waypoint,
            Association.child_document_id == Waypoint.document_id). \
        cte('waypoint_grandchildren')

    return union(
            select_waypoint.select(),
            select_waypoint_children.select(),
            select_waypoint_grandchildren.select()). \
        cte('select_all_waypoints')


@resource(path='/waypoints/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class WaypointVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveWaypoint, ArchiveWaypointLocale, schema_waypoint,
            schema_adaptor)


def update_linked_route_titles(waypoint, update_types, user_id):
    """When a waypoint is the main waypoint of a route, the field
    `title_prefix`, which caches the waypoint name, has to be updated.
    This method takes care of updating all routes, that the waypoint is
    "main waypoint" of.
    """
    if UpdateType.LANG not in update_types:
        # if the locales did not change, no need to continue
        return

    linked_routes = DBSession.query(Route). \
        filter(Route.main_waypoint_id == waypoint.document_id). \
        options(joinedload(Route.locales).load_only(
            RouteLocale.lang, RouteLocale.id)). \
        options(load_only(Route.document_id)). \
        all()

    if linked_routes:
        waypoint_locales = waypoint.locales
        waypoint_locales_index = {
            locale.lang: locale for locale in waypoint_locales}

        for route in linked_routes:
            set_route_title_prefix(
                route, waypoint_locales, waypoint_locales_index)
