import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint
from c2corg_common.fields_outing import fields_outing
from cornice.resource import resource, view


from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_common.attributes import activities
from sqlalchemy.sql.expression import exists

validate_route_create = make_validator_create(
    fields_outing, 'activities', activities, document_field='outing')
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)


def validate_associations(request):
    """Check if the given waypoint and route id are valid.
    """
    waypoint_id = request.validated.get('waypoint_id')
    if waypoint_id:
        waypoint_exists = DBSession.query(
            exists().where(Waypoint.document_id == waypoint_id)).scalar()
        if not waypoint_exists:
            request.errors.add(
                'body', 'waypoint_id', 'waypoint does not exist')

    route_id = request.validated.get('route_id')
    if route_id:
        route_exists = DBSession.query(
            exists().where(Route.document_id == route_id)).scalar()
        if not route_exists:
            request.errors.add(
                'body', 'route_id', 'route does not exist')

    user_ids = request.validated.get('user_ids')
    if user_ids:
        for user_id in user_ids:
            user_exists = DBSession.query(
                exists().where(User.id == user_id)).scalar()
            if not user_exists:
                request.errors.add(
                    'body', 'user_ids',
                    'user "{0:n}" does not exist'.format(user_id))


def adapt_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_outing, activities, field_list_type)
    return restrict_schema(schema_outing, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'listing')


@resource(collection_path='/outings', path='/outings/{id}',
          cors_policy=cors_policy)
class OutingRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            Outing, schema_outing, listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Outing, schema_outing, schema_adaptor)

    @restricted_json_view(schema=schema_create_outing,
                          validators=[validate_route_create,
                                      validate_associations])
    def collection_post(self):
        create_associations = functools.partial(
            add_associations,
            self.request.validated['waypoint_id'],
            self.request.validated['route_id'],
            self.request.validated['user_ids']
        )
        return self._collection_post(
            schema_outing, document_field='outing',
            after_add=create_associations)

    @restricted_json_view(schema=schema_update_outing,
                          validators=[validate_id, validate_outing_update])
    def put(self):
        return self._put(Outing, schema_outing)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, ArchiveOutingLocale, schema_outing, schema_adaptor)


def add_associations(waypoint_id, route_id, user_ids, outing):
    """When creating a new outing, associations to the linked waypoint, route
    and users are set up at the same time.
    """
    DBSession.add(Association(
        parent_document_id=waypoint_id, child_document_id=outing.document_id))
    DBSession.add(Association(
        parent_document_id=route_id, child_document_id=outing.document_id))
    for user_id in user_ids:
        DBSession.add(Association(
            parent_document_id=user_id, child_document_id=outing.document_id))
