from cornice.resource import resource, view

from c2corg_api.models.image import Image, schema_image, schema_update_image
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param


@resource(collection_path='/images', path='/images/{id}',
          cors_policy=cors_policy)
class ImageRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Image, schema_image)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Image, schema_image)

    @restricted_json_view(schema=schema_image)
    def collection_post(self):
        return self._collection_post(schema_image)

    @restricted_json_view(schema=schema_update_image, validators=validate_id)
    def put(self):
        return self._put(Image, schema_image)
