from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.outing import schema_association_outing, Outing
from c2corg_api.views.outing import set_author
from cornice.resource import resource, view

from c2corg_api.models.route import Route, schema_route, schema_update_route, \
    ArchiveRoute, ArchiveRouteLocale, RouteLocale
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields, \
    NUM_RECENT_OUTINGS
from c2corg_api.views import cors_policy, restricted_json_view, \
    get_best_locale, to_json_dict, set_best_locale
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_common.fields_route import fields_route
from c2corg_common.attributes import activities
from sqlalchemy.orm import load_only, joinedload

validate_route_create = make_validator_create(
    fields_route, 'activities', activities)
validate_route_update = make_validator_update(
    fields_route, 'activities', activities)


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
            Route, schema_route, listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(
            Route, schema_route, schema_adaptor,
            set_custom_associations=RouteRest.set_recent_outings)

    @restricted_json_view(schema=schema_route,
                          validators=validate_route_create)
    def collection_post(self):
        return self._collection_post(schema_route, after_add=init_title_prefix)

    @restricted_json_view(schema=schema_update_route,
                          validators=[validate_id, validate_route_update])
    def put(self):
        return self._put(Route, schema_route, after_update=update_title_prefix)

    @staticmethod
    def set_recent_outings(route, lang):
        """Set last 10 outings on the given route.
        """
        recent_outings = DBSession.query(Outing). \
            join(
                Association,
                Outing.document_id == Association.child_document_id). \
            filter(Association.parent_document_id == route.document_id). \
            options(load_only(
                Outing.document_id, Outing.activities, Outing.date_start,
                Outing.date_end, Outing.version)). \
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
class RouteVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveRoute, ArchiveRouteLocale, schema_route, schema_adaptor)


def init_title_prefix(route):
    update_title_prefix(route, create=True)


def update_title_prefix(route, create=False):
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
