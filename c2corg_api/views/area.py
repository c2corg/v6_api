from c2corg_api.models.area import schema_area, Area, schema_update_area
from c2corg_common.fields_area import fields_area
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param


validate_area_create = make_validator_create(fields_area.get('required'))
validate_area_update = make_validator_update(fields_area.get('required'))


@resource(collection_path='/areas', path='/areas/{id}',
          cors_policy=cors_policy)
class AreaRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Area, schema_area)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Area, schema_area)

    @restricted_json_view(
            schema=schema_area, validators=validate_area_create)
    def collection_post(self):
        # TODO limit to moderators
        return self._collection_post(Area, schema_area)

    @restricted_json_view(
            schema=schema_update_area,
            validators=[validate_id, validate_area_update])
    def put(self):
        # TODO limit to moderators
        return self._put(Area, schema_area)
