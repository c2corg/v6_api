import functools
from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale, OUTING_TYPE
from c2corg_api.models.utils import get_mid_point
from c2corg_api.views import cors_policy, restricted_json_view, \
    set_default_geom_from_associations
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import outing_documents_config, \
    outing_schema_adaptor
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations, \
    has_permission_for_outing
from c2corg_common.attributes import activities
from c2corg_common.fields_outing import fields_outing
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPForbidden

validate_outing_create = make_validator_create(
    fields_outing, 'activities', activities)
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, OUTING_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, OUTING_TYPE, False)


def validate_required_associations(request, **kwargs):
    missing_user = False
    missing_route = False

    associations = request.validated.get('associations', None)
    if not associations:
        missing_user = True
        missing_route = True
    else:
        linked_routes = associations.get('routes', [])
        if not linked_routes:
            missing_route = True

        linked_users = associations.get('users', [])
        if not linked_users:
            missing_user = True

    if missing_user:
        request.errors.add(
            'body', 'associations.users', 'at least one user required')

    if missing_route:
        request.errors.add(
            'body', 'associations.routes', 'at least one route required')


@resource(collection_path='/outings', path='/outings/{id}',
          cors_policy=cors_policy)
class OutingRest(DocumentRest):

    @view(validators=[
        validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(OUTING_TYPE, outing_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(
            Outing, schema_outing, adapt_schema=outing_schema_adaptor)

    @restricted_json_view(
        schema=schema_create_outing,
        validators=[
            colander_body_validator,
            validate_outing_create,
            validate_associations_create,
            validate_required_associations])
    def collection_post(self):
        set_default_geom = functools.partial(
            set_default_geometry,
            self.request.validated['associations']['routes']
        )
        return self._collection_post(
            schema_outing, before_add=set_default_geom)

    @restricted_json_view(
        schema=schema_update_outing,
        validators=[
            colander_body_validator,
            validate_id,
            validate_outing_update,
            validate_associations_update,
            validate_required_associations])
    def put(self):
        if not has_permission_for_outing(
                self.request, self.request.validated['id']):
            # moderators can change every outing, but a normal user can only
            # change an outing that they are associated to
            raise HTTPForbidden('No permission to change this outing')
        return self._put(
            Outing, schema_outing,
            before_update=functools.partial(
                update_default_geometry,
                self.request.validated['associations']['routes']))


@resource(path='/outings/{id}/{lang}/info', cors_policy=cors_policy)
class OutingInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Outing)


def set_default_geometry(linked_routes, outing, user_id):
    """When creating a new outing, set the default geometry to the middle point
    of a given track, if not to the centroid of the convex hull
    of all associated routes.
    """
    if outing.geometry is not None and outing.geometry.geom is not None:
        # default geometry already set
        return

    if outing.geometry is not None and outing.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)
        return

    set_default_geom_from_associations(outing, linked_routes)


def update_default_geometry(linked_routes, outing, outing_in, user_id):
    """When updating an outing, set the default geometry to the middle point
    of a new track, if not to the centroid of the convex hull
    of all associated routes.
    """
    geometry = outing.geometry
    geometry_in = outing_in.geometry
    if geometry_in is not None and geometry_in.geom is not None:
        # default geom is manually set in the request
        return
    elif geometry_in is not None and geometry_in.geom_detail is not None:
        # update the default geom with the new track
        geometry.geom = get_mid_point(geometry.geom_detail)
        return
    elif geometry is not None and geometry.geom_detail is not None:
        # default geom is already set and no new track is provided
        return

    set_default_geom_from_associations(
        outing, linked_routes, update_always=True)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, ArchiveOutingLocale, schema_outing,
            outing_schema_adaptor)
