import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import UpdateType
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.views.document_associations import get_first_column
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import waypoint_documents_config, \
    waypoint_schema_adaptor, outing_documents_config, route_documents_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.route import set_route_title_prefix, \
    update_pt_rating
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint,
    ArchiveWaypoint, ArchiveWaypointLocale, WAYPOINT_TYPE,
    schema_create_waypoint)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update,
    NUM_RECENT_OUTINGS)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations, validate_cook_param
from c2corg_api.models.common.fields_waypoint import fields_waypoint
from c2corg_api.models.common.attributes import waypoint_types
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy.orm.util import aliased
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import and_, text, union, column

# the number of routes that are included for waypoints
NUM_ROUTES = 400

validate_waypoint_create = make_validator_create(
    fields_waypoint, 'waypoint_type', waypoint_types)
validate_waypoint_update = make_validator_update(
    fields_waypoint, 'waypoint_type', waypoint_types)
validate_associations_create = functools.partial(
    validate_associations, WAYPOINT_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, WAYPOINT_TYPE, False)


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
        return self._collection_get(WAYPOINT_TYPE, waypoint_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
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

            `cook=...` (optional)
            Get the document for viewing in a lang. Response may contains
            another lang if requested one does not exists


        """
        return self._get(
            waypoint_documents_config, schema_waypoint,
            adapt_schema=waypoint_schema_adaptor, include_maps=True,
            set_custom_associations=set_custom_associations)

    @restricted_json_view(schema=schema_create_waypoint,
                          validators=[
                              colander_body_validator,
                              validate_waypoint_create,
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
                          validators=[
                              colander_body_validator,
                              validate_id,
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
            Waypoint, schema_waypoint, after_update=update_linked_routes)


def set_custom_associations(waypoint, lang):
    set_recent_outings(waypoint, lang)
    set_linked_routes(waypoint, lang)


def set_recent_outings(waypoint, lang):
    """Set last 10 outings on routes associated to the given waypoint.
    """
    t_outing_route = aliased(Association, name='a1')
    t_route_wp = aliased(Association, name='a2')
    with_query_waypoints = _get_select_children(waypoint)

    recent_outing_ids = get_first_column(
        DBSession.query(Outing.document_id).
        filter(Outing.redirects_to.is_(None)).
        join(
            t_outing_route,
            Outing.document_id == t_outing_route.child_document_id).
        join(
            t_route_wp,
            and_(
                t_route_wp.child_document_id ==
                t_outing_route.parent_document_id,
                t_route_wp.child_document_type == ROUTE_TYPE,
            )).
        join(
            with_query_waypoints,
            with_query_waypoints.c.document_id == t_route_wp.parent_document_id
        ).
        distinct().
        order_by(Outing.date_end.desc()).
        limit(NUM_RECENT_OUTINGS).
        all())

    total = DBSession.query(Outing.document_id). \
        filter(Outing.redirects_to.is_(None)). \
        join(
            t_outing_route,
            Outing.document_id == t_outing_route.child_document_id). \
        join(
            t_route_wp,
            and_(
                t_route_wp.child_document_id ==
                t_outing_route.parent_document_id,
                t_route_wp.child_document_type == ROUTE_TYPE,
            )). \
        join(
            with_query_waypoints,
            with_query_waypoints.c.document_id == t_route_wp.parent_document_id
        ). \
        distinct(). \
        count()

    waypoint.associations['recent_outings'] = get_documents_for_ids(
        recent_outing_ids, lang, outing_documents_config, total)


def set_linked_routes(waypoint, lang):
    """
    Set associated routes for the given waypoint including associated routes
    of child and grandchild waypoints.
    Note that this function returns a dict and not a list!
    """
    with_query_waypoints = _get_select_children(waypoint)

    route_ids = get_first_column(
        DBSession.query(Route.document_id).
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
        distinct(Route.document_id).
        limit(NUM_ROUTES).
        all())

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
        distinct(). \
        count()

    waypoint.associations['all_routes'] = get_documents_for_ids(
        route_ids, lang, route_documents_config, total)


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
        query(
            Association.child_document_id.label('document_id')). \
        filter(
            and_(Association.child_document_type == WAYPOINT_TYPE,
                 Association.parent_document_id == waypoint.document_id)). \
        cte('waypoint_children')
    # query to get the grand-child waypoints
    select_waypoint_grandchildren = DBSession. \
        query(
            Association.child_document_id.label('document_id')). \
        select_from(select_waypoint_children). \
        join(
            Association,
            and_(
                Association.parent_document_id ==
                select_waypoint_children.c.document_id,
                Association.child_document_type == WAYPOINT_TYPE
            )). \
        cte('waypoint_grandchildren')

    return union(
            select_waypoint.select(),
            select_waypoint_children.select(),
            select_waypoint_grandchildren.select()). \
        cte('select_all_waypoints')


@resource(path='/waypoints/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class WaypointVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveWaypoint, WAYPOINT_TYPE, ArchiveWaypointLocale,
            schema_waypoint, waypoint_schema_adaptor)


@resource(path='/waypoints/{id}/{lang}/info', cors_policy=cors_policy)
class WaypointInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(waypoint_documents_config)


def update_linked_routes(waypoint, update_types, user_id):
    update_linked_route_titles(waypoint, update_types, user_id)
    update_linked_routes_public_transportation_rating(waypoint, update_types)


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


def update_linked_routes_public_transportation_rating(waypoint, update_types):
    if (
        waypoint.waypoint_type != "access"
        or "public_transportation_rating" not in update_types
    ):
        return

    route_type = text('\'' + ROUTE_TYPE + '\'')

    # Get all parent routes
    parent_routes = DBSession. \
        query(
            Association.parent_document_id.label('route_id')
        ) \
        .filter(Association.parent_document_type == route_type) \
        .filter(Association.child_document_id == waypoint.document_id) \
        .subquery()
    # Get all children routes
    children_routes = DBSession. \
        query(
            Association.child_document_id.label('route_id')
        ) \
        .filter(Association.child_document_type == route_type) \
        .filter(Association.parent_document_id == waypoint.document_id) \
        .subquery()
    # Merge all routes
    routes = DBSession \
        .query(Route) \
        .select_from(union(parent_routes.select(), children_routes.select())) \
        .join(Route, Route.document_id == column('route_id')) \
        .all()

    for route in routes:
        update_pt_rating(route)
