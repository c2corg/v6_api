from c2corg_api.models.image import Image, schema_image, schema_update_image
from c2corg_common.fields_image import fields_image
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param

validate_image_create = make_validator_create(fields_image.get('required'))
validate_image_update = make_validator_update(fields_image.get('required'))


@resource(collection_path='/images', path='/images/{id}',
          cors_policy=cors_policy)
class ImageRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Image, schema_image)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Image, schema_image)

    @restricted_json_view(
            schema=schema_image, validators=validate_image_create)
    def collection_post(self):
        return self._collection_post(schema_image)

    @restricted_json_view(
            schema=schema_update_image,
            validators=[validate_id, validate_image_update])
    def put(self):
        # FIXME: personal images should only be modifiable by
        # their creator and moderators
        return self._put(Image, schema_image)
