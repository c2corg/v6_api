import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.outing import schema_association_outing, Outing
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.outing import set_author
from c2corg_api.models.utils import get_mid_point
from cornice.resource import resource, view

from c2corg_api.models.route import Route, schema_route, schema_update_route, \
    ArchiveRoute, ArchiveRouteLocale, RouteLocale, ROUTE_TYPE, \
    schema_create_route
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields, \
    NUM_RECENT_OUTINGS
from c2corg_api.views import cors_policy, restricted_json_view, \
    get_best_locale, to_json_dict, set_best_locale
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations
from c2corg_common.fields_route import fields_route
from c2corg_common.attributes import activities
from sqlalchemy.orm import load_only, joinedload

validate_route_create = make_validator_create(
    fields_route, 'activities', activities)
validate_route_update = make_validator_update(
    fields_route, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, ROUTE_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, ROUTE_TYPE, False)


def validate_main_waypoint(is_on_create, request):
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


def adapt_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_route, activities, field_list_type)
    return restrict_schema(schema_route, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'listing')


@resource(collection_path='/routes', path='/routes/{id}',
          cors_policy=cors_policy)
class RouteRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            Route, schema_route, ROUTE_TYPE, clazz_locale=RouteLocale,
            adapt_schema=listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(
            Route, schema_route, clazz_locale=RouteLocale,
            adapt_schema=schema_adaptor, include_maps=True,
            set_custom_associations=RouteRest.set_recent_outings)

    @restricted_json_view(
        schema=schema_create_route,
        validators=[validate_route_create,
                    validate_associations_create,
                    functools.partial(validate_main_waypoint, True)])
    def collection_post(self):
        return self._collection_post(
            schema_route, before_add=set_default_geometry,
            after_add=init_title_prefix)

    @restricted_json_view(
        schema=schema_update_route,
        validators=[validate_id,
                    validate_route_update,
                    validate_associations_update,
                    functools.partial(validate_main_waypoint, False)])
    def put(self):
        old_main_waypoint_id = DBSession.query(Route.main_waypoint_id). \
            filter(Route.document_id == self.request.validated['id']).scalar()
        return self._put(
            Route, schema_route,
            before_update=functools.partial(
                update_default_geometry, old_main_waypoint_id),
            after_update=update_title_prefix)

    @staticmethod
    def set_recent_outings(route, lang):
        """Set last 10 outings on the given route.
        """
        recent_outings = DBSession.query(Outing). \
            filter(Outing.redirects_to.is_(None)). \
            join(
                Association,
                Outing.document_id == Association.child_document_id). \
            filter(Association.parent_document_id == route.document_id). \
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
                Association,
                Outing.document_id == Association.child_document_id). \
            filter(Association.parent_document_id == route.document_id). \
            count()

        route.associations['recent_outings'] = {
            'outings': [
                to_json_dict(user, schema_association_outing)
                for user in recent_outings
            ],
            'total': total
        }


@resource(path='/routes/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class RouteVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveRoute, ArchiveRouteLocale, schema_route, schema_adaptor)


@resource(path='/routes/{id}/{lang}/info', cors_policy=cors_policy)
class RouteInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Route)


def set_default_geometry(route, user_id):
    """When creating a new route, set the default geometry to the middle point
    of a given track, if not to the geometry of the associated main waypoint.
    """
    if route.geometry is not None and route.geometry.geom is not None:
        # default geometry already set
        return

    if route.geometry is not None and route.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        route.geometry.geom = get_mid_point(route.geometry.geom_detail)
    elif route.main_waypoint_id:
        # get default point from main waypoint
        main_wp_point = DBSession.query(DocumentGeometry.geom).filter(
            DocumentGeometry.document_id == route.main_waypoint_id).scalar()
        if main_wp_point is not None:
            route.geometry = DocumentGeometry(geom=main_wp_point)


def update_default_geometry(old_main_waypoint_id, route, route_in, user_id):
    geometry_in = route_in.geometry
    if geometry_in is not None and geometry_in.geom is not None:
        # default geom is manually set in the request
        return
    elif geometry_in is not None and geometry_in.geom_detail is not None:
        # update the default geom with the new track
        route.geometry.geom = get_mid_point(route.geometry.geom_detail)
    elif main_waypoint_has_changed(route_in, old_main_waypoint_id):
        # when the main waypoint has changed, use the waypoint geom
        main_wp_point = DBSession.query(DocumentGeometry.geom).filter(
            DocumentGeometry.document_id == route.main_waypoint_id).scalar()
        if main_wp_point is not None:
            if route.geometry is not None:
                if route.geometry.geom_detail is None:
                    # only update if no own track
                    route.geometry.geom = main_wp_point
            else:
                route.geometry = DocumentGeometry(geom=main_wp_point)


def main_waypoint_has_changed(route, old_main_waypoint_id):
    if route.main_waypoint_id is None:
        return False
    else:
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
