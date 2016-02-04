from c2corg_api.models.area import schema_area, Area, schema_update_area
from c2corg_api.models.area_association import update_area
from c2corg_api.models.document import UpdateType
from c2corg_common.fields_area import fields_area
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param
from pyramid.httpexceptions import HTTPBadRequest

validate_area_create = make_validator_create(fields_area.get('required'))
validate_area_update = make_validator_update(fields_area.get('required'))


@resource(collection_path='/areas', path='/areas/{id}',
          cors_policy=cors_policy)
class AreaRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Area, schema_area, include_areas=False)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Area, schema_area, include_areas=False)

    @restricted_json_view(
            schema=schema_area, validators=validate_area_create,
            permission='moderator')
    def collection_post(self):
        return self._collection_post(
            Area, schema_area, after_add=insert_associations)

    @restricted_json_view(
            schema=schema_update_area,
            validators=[validate_id, validate_area_update])
    def put(self):
        if not self.request.has_permission('moderator'):
            # the geometry of areas should not be modifiable for non-moderators
            if self.request.validated['document'] and \
                    self.request.validated['document']['geometry']:
                raise HTTPBadRequest('No permission to change the geometry')

        return self._put(Area, schema_area, after_update=update_associations)


def insert_associations(area):
    """Create links between this new area and documents.
    """
    update_area(area, reset=False)


def update_associations(area, update_types):
    """Update the links between this area and documents when the geometry
    has changed.
    """
    if UpdateType.GEOM in update_types:
        update_area(area, reset=True)
