import logging

import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.outing import Outing
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
    get_best_locale, set_default_geom_from_associations
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations, validate_cook_param
from c2corg_common.fields_route import fields_route
from c2corg_common.attributes import activities
from sqlalchemy.orm import load_only

log = logging.getLogger(__name__)

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
        'body', 'main_waypoint_id', 'no association for the main waypoint')


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
            after_add=init_title_prefix)

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
                         after_update=update_title_prefix)

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


def init_title_prefix(route, user_id):
    check_title_prefix(route, create=True)


def update_title_prefix(route, update_types, user_id):
    check_title_prefix(route)


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
    set_title_prefix_for_ids([l.id for l in route.locales], title)


def set_title_prefix_for_ids(ids, title):
    """Set the given title as `prefix_title` for all route locales with
    the given ids.
    """
    DBSession.query(RouteLocale).filter(RouteLocale.id.in_(ids)). \
        update({RouteLocale.title_prefix: title}, synchronize_session=False)
