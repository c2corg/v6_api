from itertools import combinations

import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.outing import Outing
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.views.document_associations import get_first_column
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import route_documents_config, \
    route_schema_adaptor, outing_documents_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.models.utils import get_mid_point
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.models.route import Route, schema_route, schema_update_route, \
    ArchiveRoute, ArchiveRouteLocale, RouteLocale, ROUTE_TYPE, \
    schema_create_route
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, NUM_RECENT_OUTINGS
from c2corg_api.views import cors_policy, restricted_json_view, \
    get_best_locale, restricted_view, set_default_geom_from_associations
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations, validate_cook_param
from c2corg_api.models.common.fields_route import fields_route
from c2corg_api.models.common.attributes import activities, \
    public_transportation_ratings
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import text, or_, column, union

validate_route_create = make_validator_create(
    fields_route, 'activities', activities)
validate_route_update = make_validator_update(
    fields_route, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, ROUTE_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, ROUTE_TYPE, False)


def validate_main_waypoint(is_on_create, request, **kwargs):
    """ Check that the document given as main waypoint is also listed as
    association.
    """
    doc = request.validated if is_on_create else \
        request.validated.get('document', {})
    main_waypoint_id = doc.get('main_waypoint_id', None)

    if not main_waypoint_id:
        return

    associations = request.validated.get('associations', None)
    if associations:
        linked_waypoints = associations.get('waypoints', [])
        for linked_wp in linked_waypoints:
            if linked_wp['document_id'] == main_waypoint_id:
                # there is an association for the main waypoint
                return

    # no association found
    request.errors.add(
        'body', 'main_waypoint_id', 'no association to the main waypoint')


def validate_required_associations(request, **kwargs):
    missing_waypoint = False

    associations = request.validated.get('associations', None)
    if not associations:
        missing_waypoint = True
    else:
        linked_waypoints = associations.get('waypoints', [])
        if not linked_waypoints:
            missing_waypoint = True

    if missing_waypoint:
        request.errors.add(
            'body', 'associations.waypoints', 'at least one waypoint required')


@resource(collection_path='/routes', path='/routes/{id}',
          cors_policy=cors_policy)
class RouteRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(ROUTE_TYPE, route_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            route_documents_config, schema_route, clazz_locale=RouteLocale,
            adapt_schema=route_schema_adaptor, include_maps=True,
            set_custom_associations=RouteRest.set_recent_outings)

    @restricted_json_view(
        schema=schema_create_route,
        validators=[
            colander_body_validator,
            validate_route_create,
            validate_associations_create,
            validate_required_associations,
            functools.partial(validate_main_waypoint, True)])
    def collection_post(self):
        linked_waypoints = self.request.validated. \
            get('associations', {}).get('waypoints', [])
        return self._collection_post(
            schema_route,
            before_add=functools.partial(
                set_default_geometry, linked_waypoints),
            after_add=init_linked_attributes)

    @restricted_json_view(
        schema=schema_update_route,
        validators=[
            colander_body_validator,
            validate_id,
            validate_route_update,
            validate_associations_update,
            validate_required_associations,
            functools.partial(validate_main_waypoint, False)])
    def put(self):
        return self._put(Route,
                         schema_route,
                         before_update=update_default_geometry,
                         after_update=update_linked_attributes)

    @staticmethod
    def set_recent_outings(route, lang):
        """Set last 10 outings on the given route.
        """
        recent_outing_ids = get_first_column(
            DBSession.query(Outing.document_id).
            filter(Outing.redirects_to.is_(None)).
            join(
                Association,
                Outing.document_id == Association.child_document_id).
            filter(Association.parent_document_id == route.document_id).
            distinct().
            order_by(Outing.date_end.desc()).
            limit(NUM_RECENT_OUTINGS).
            all())

        total = DBSession.query(Outing.document_id). \
            filter(Outing.redirects_to.is_(None)). \
            join(
                Association,
                Outing.document_id == Association.child_document_id). \
            filter(Association.parent_document_id == route.document_id). \
            distinct(). \
            count()

        route.associations['recent_outings'] = get_documents_for_ids(
            recent_outing_ids, lang, outing_documents_config, total)


@resource(path='/routes/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class RouteVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveRoute, ROUTE_TYPE, ArchiveRouteLocale, schema_route,
            route_schema_adaptor)


@resource(path='/routes/{id}/{lang}/info', cors_policy=cors_policy)
class RouteInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(route_documents_config)


@resource(path="/routes/update_public_transportation_rating",
          cors_policy=cors_policy)
class RoutePublicTransportationRatingRest(object):
    """
    Update all route public transportation rating

    Request:
        `GET` `/update_public_transportation_rating?waypoint_extrapolation=...`


    Parameters:
        `waypoint_extrapolation=true` (optional)
        extrapolate starting and ending points
        allows to reset public_transportation_rating values
        set to true by default
    """

    def __init__(self, request):
        self.request = request

    @restricted_view(permission='moderator')
    def get(self):
        waypoint_extrapolation = self.request.params.get(
            'waypoint_extrapolation') or True
        update_all_pt_rating(waypoint_extrapolation)


def set_default_geometry(linked_waypoints, route, user_id):
    """When creating a new route, set the default geometry to the middle point
    of a given track, if not to the geometry of the associated main waypoint
    (if a main waypoint is set), otherwise to the centroid of the convex hull
    of all associated waypoints.
    """
    if route.geometry is not None and route.geometry.geom is not None:
        # default geometry already set
        return

    if route.geometry is not None and route.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        route.geometry.geom = get_mid_point(route.geometry.geom_detail)
    elif route.main_waypoint_id:
        _set_default_geom_from_main_wp(route)

    set_default_geom_from_associations(route, linked_waypoints)


def _set_default_geom_from_main_wp(route):
    main_wp_point = _get_default_geom_from_main_wp(route)
    if main_wp_point is not None:
        route.geometry = DocumentGeometry(geom=main_wp_point)


def _get_default_geom_from_main_wp(route):
    return DBSession.query(DocumentGeometry.geom).filter(
        DocumentGeometry.document_id == route.main_waypoint_id).scalar()


def update_default_geometry(route, route_in):
    geometry = route.geometry
    geometry_in = route_in.geometry

    if geometry_in is None:
        # new payload does not have geometry => copy old geometry
        route_in.geometry = route.geometry
    elif geometry_in.geom is None and geometry is not None:
        # else, both geometry is set, but new geometry dos not have
        # geom attribute => copy old geom attribute
        geometry_in.geom = geometry.geom


def main_waypoint_has_changed(route, old_main_waypoint_id):
    return old_main_waypoint_id != route.main_waypoint_id


def init_linked_attributes(route, user_id):
    check_title_prefix(route, create=True)
    update_pt_rating(route)


def update_linked_attributes(route, update_types, user_id):
    check_title_prefix(route)
    update_pt_rating(route)


def check_title_prefix(route, create=False):
    """The field `main_waypoint_id` indicates the main waypoint of a
     route. If given, the title of this waypoint is cached in
     RouteLocale.title_prefix. This method takes care of setting this field.
    """
    if route.main_waypoint_id is None and not create:
        # no main waypoint is set, set the `title_prefix` to ''
        set_title_prefix(route, '')
    else:
        # otherwise get the main waypoint locales and select the "best"
        # waypoint locale for each route locale. E.g. for a route locale in
        # "fr", we also try to get the waypoint locale in "fr" (if not the
        # "next" locale).
        waypoint_locales = DBSession.query(DocumentLocale). \
            filter(DocumentLocale.document_id == route.main_waypoint_id). \
            options(load_only(DocumentLocale.lang, DocumentLocale.title)). \
            all()
        waypoint_locales_index = {
            locale.lang: locale for locale in waypoint_locales}

        set_route_title_prefix(route, waypoint_locales, waypoint_locales_index)


def set_route_title_prefix(route, waypoint_locales, waypoint_locales_index):
    """Sets the `title_prefix` of all locales of the given route using the
    provided waypoint locales.
    """
    if len(waypoint_locales) == 1:
        set_title_prefix(route, waypoint_locales[0].title)
    else:
        for locale in route.locales:
            waypoint_locale = get_best_locale(
                waypoint_locales_index, locale.lang)
            set_title_prefix_for_ids(
                [locale.id],
                waypoint_locale.title if waypoint_locale else '')


def set_title_prefix(route, title):
    """Set the given title as `prefix_title` for all locales of the given
    route.
    """
    set_title_prefix_for_ids([locale.id for locale in route.locales], title)


def set_title_prefix_for_ids(ids, title):
    """Set the given title as `prefix_title` for all route locales with
    the given ids.
    """
    DBSession.query(RouteLocale).filter(RouteLocale.id.in_(ids)). \
        update({RouteLocale.title_prefix: title}, synchronize_session=False)


def update_all_pt_rating(waypoint_extrapolation=True):
    """ Update the public transportation rating of every routes
    based on linked waypoints
    Warning: this is a very heavy request to run, check logs levels before use:
    - avoid debug/info level for python
    - avoir all level for postgresql (prefer log_statement = 'ddl')
    """
    route_type = text('\'' + ROUTE_TYPE + '\'')
    waypoint_type = text('\'' + WAYPOINT_TYPE + '\'')

    # Get all routes parent of an access waypoint
    parent_routes = DBSession. \
        query(
            Association.parent_document_id.label('route_id')
        ) \
        .filter(Association.parent_document_type == route_type) \
        .filter(Association.child_document_type == waypoint_type) \
        .join(
            Waypoint,
            Waypoint.document_id == Association.child_document_id
        ) \
        .filter(Waypoint.waypoint_type == 'access') \
        .subquery()
    # Get all routes children of an access waypoint
    children_routes = DBSession. \
        query(
            Association.child_document_id.label('route_id')
        ) \
        .filter(Association.child_document_type == route_type) \
        .filter(Association.parent_document_type == waypoint_type) \
        .join(
            Waypoint,
            Waypoint.document_id == Association.parent_document_id
        ) \
        .filter(Waypoint.waypoint_type == 'access') \
        .subquery()
    # Merge all routes
    routes = DBSession \
        .query(Route) \
        .select_from(union(parent_routes.select(), children_routes.select())) \
        .join(Route, Route.document_id == column('route_id')) \
        .all()

    for route in routes:
        update_pt_rating(route, waypoint_extrapolation)

    return True


def update_pt_rating(route, waypoint_extrapolation=True):
    """Update public transportation rating
    based on provided ending and starting waypoints
    If none are provided, an extrapolation can be done
    """

    if waypoint_extrapolation:
        linked_access_waypoints = _get_linked_waypoints_pt_ratings(route)
        starting_waypoints, ending_waypoints = \
            _find_starting_and_ending_points(
                linked_access_waypoints,
                route.route_types
            )
    else:
        starting_waypoints, ending_waypoints = [], []

    public_transportation_rating = _pt_rating(
        starting_waypoints, ending_waypoints, route.route_types)

    DBSession.query(Route) \
        .filter(Route.document_id == route.document_id) \
        .update({Route.public_transportation_rating:
                public_transportation_rating},
                synchronize_session=False
                )


def _get_linked_waypoints_pt_ratings(route):
    """ Get all linked waypoints linked to a route
    """
    waypoint_type = text('\'' + WAYPOINT_TYPE + '\'')

    linked_access_waypoints = DBSession. \
        query(
            Waypoint
        ) \
        .select_from(Association) \
        .filter(or_(
            Association.parent_document_id == route.document_id,
            Association.child_document_id == route.document_id,
        )) \
        .filter(or_(
            Association.child_document_type == waypoint_type,
            Association.parent_document_type == waypoint_type,
        )) \
        .join(Waypoint, or_(
            Waypoint.document_id == Association.child_document_id,
            Waypoint.document_id == Association.parent_document_id
        )) \
        .filter(Waypoint.waypoint_type == 'access') \
        .all()
    return linked_access_waypoints


def _find_starting_and_ending_points(waypoints, route_types):
    """Extrapolation of starting and ending waypoints
    based on the followed rules:
    - for crossings : with the two most distant access waypoints
    Calculates the distance between all pairs of points
    using shapely's distance() method
    and returns the pair with the maximum distance.
    - for loops : with all the access waypoints
    - for others route type :
    only if a single access waypoint is linked to the route
    """
    if route_types and bool(
        set(["loop", "loop_hut", "return_same_way"]) & set(route_types)
    ):
        return waypoints, []
    elif (
        route_types
        and bool(set(["traverse", "raid", "expedition"]) & set(route_types))
        and len(waypoints) >= 2
    ):
        if len(waypoints) == 2:
            return [waypoints[0]], [waypoints[1]]
        # Initialize variables to store
        # the most distant points and their distance
        max_dist = 0
        most_distant_points = None

        # Generate combinations of points
        point_combinations = combinations(waypoints, 2)

        # Iterate through combinations to find the most distant points
        for w1, w2 in point_combinations:
            dist = w1.geometry.distance(w1.geometry.geom, w2.geometry.geom)
            if dist > max_dist:
                max_dist = dist
                most_distant_points = (w1, w2)

        return [most_distant_points[0]], [most_distant_points[1]]
    elif len(waypoints) == 1:
        return [waypoints[0]], []
    else:
        return [], []


def _pt_rating(starting_waypoints, ending_waypoints, route_types):
    """Take best public transportation rating value of each array
    (starting_waypoint and ending_waypoints)
    and keep the worst of the two values
    If no waypoint is provided, assume default service (unknown)
    """
    #  If no starting point is provided
    if len(starting_waypoints) == 0:
        return 'unknown service'

    # Function to convert rating to its index in the enum
    def rating_index(rating):
        if rating is None:
            return public_transportation_ratings.index('unknown service')
        return public_transportation_ratings.index(rating)

    # Function to get the best rating between two ratings
    def best_rating(rating1, rating2):
        return public_transportation_ratings[
            min(rating_index(rating1), rating_index(rating2))
        ]

    # Function to get the worst rating between two ratings
    def worst_rating(rating1, rating2):
        return public_transportation_ratings[
            max(rating_index(rating1), rating_index(rating2))
        ]

    # Initialize variables to hold best ratings
    best_starting_rating = 'no service'
    best_ending_rating = 'no service'

    # Iterate through starting waypoints
    for waypoint in starting_waypoints:
        best_starting_rating = best_rating(
            best_starting_rating, waypoint.public_transportation_rating)

    # Return the best starting rating if it's not a crossing
    if not (route_types and bool(
            set(["traverse", "raid", "expedition"]) & set(route_types)
            )):
        return best_starting_rating

    # If no ending point is provided
    if (len(ending_waypoints) == 0):
        return 'unknown service'

    # Iterate through ending waypoints
    for waypoint in ending_waypoints:
        best_ending_rating = best_rating(
            best_ending_rating, waypoint.public_transportation_rating)

    # Return the worst of the two ratings
    return worst_rating(best_starting_rating, best_ending_rating)
