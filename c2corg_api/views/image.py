import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.image import Image, schema_image, schema_update_image, \
    schema_listing_image, IMAGE_TYPE, schema_create_image
from c2corg_common.fields_image import fields_image
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound, HTTPBadRequest

validate_image_create = make_validator_create(fields_image.get('required'))
validate_image_update = make_validator_update(fields_image.get('required'))
validate_associations_create = functools.partial(
    validate_associations, IMAGE_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, IMAGE_TYPE, False)


@resource(collection_path='/images', path='/images/{id}',
          cors_policy=cors_policy)
class ImageRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(Image, schema_listing_image, IMAGE_TYPE)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Image, schema_image)

    @restricted_json_view(
            schema=schema_create_image,
            validators=[validate_image_create, validate_associations_create])
    def collection_post(self):
        return self._collection_post(schema_image)

    @restricted_json_view(
            schema=schema_update_image,
            validators=[validate_id,
                        validate_image_update,
                        validate_associations_update])
    def put(self):
        if not self.request.has_permission('moderator'):
            image_id = self.request.validated['id']
            image = DBSession.query(Image).get(image_id)
            if image is None:
                raise HTTPNotFound('No image found for id %d' % image_id)
            if image.image_type == 'collaborative':
                image_type = self.request.validated['document']['image_type']
                if image_type != image.image_type:
                    raise HTTPBadRequest(
                        'Image type cannot be changed for collaborative images'
                    )
            # personal images should only be modifiable by
            # their creator and moderators
            elif not has_been_created_by(image_id,
                                         self.request.authenticated_userid):
                raise HTTPForbidden('No permission to change this image')
        return self._put(Image, schema_image)
