from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from c2corg_api.models.image import Image, schema_image
from c2corg_api.models import DBSession
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import validate_id, to_json_dict


@resource(collection_path='/images', path='/images/{id}')
class ImageRest(DocumentRest):

    def collection_get(self):
        images = DBSession. \
            query(Image). \
            options(joinedload(Image.locales)). \
            limit(30)

        return [to_json_dict(img, schema_image) for img in images]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']

        image = DBSession. \
            query(Image). \
            filter(Image.document_id == id). \
            options(joinedload(Image.locales)). \
            first()

        return to_json_dict(image, schema_image)

    @view(schema=schema_image)
    def collection_post(self):
        image = schema_image.objectify(self.request.validated)

        DBSession.add(image)
        DBSession.flush()

        self._create_new_version(image)

        return to_json_dict(image, schema_image)
