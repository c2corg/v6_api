import functools
import os

import requests
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPFound,
    HTTPInternalServerError,
    HTTPNotFound,
)

from c2corg_api.models import DBSession
from c2corg_api.models.common.fields_image import fields_image
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.feed import update_feed_images_upload
from c2corg_api.models.image import (
    IMAGE_TYPE,
    ArchiveImage,
    Image,
    get_image_filenames,
)
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.image import (
    ImageCreateSchema,
    ImageListCreateSchema,
    ImageUpdateSchema,
    image_schema,
)
from c2corg_api.search.notify_sync import run_on_successful_transaction
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import restricted_json_view
from c2corg_api.views import set_creator as set_creator_on_documents
from c2corg_api.views.document import (
    DocumentRest,
    make_validator_create,
    make_validator_update,
    validate_document,
)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import image_documents_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.resource import resource, view
from c2corg_api.views.validation import (
    validate_associations,
    validate_associations_in,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

# Let browsers cache the redirect to the media server: the image filename
# for a given document id is stable, so the target rarely changes.
PROXY_CACHE_CONTROL = 'public, max-age=86400'


def check_filename_unique(image, request, updating):
    """Check that filename is unique."""
    if 'filename' not in image:
        return
    sql = DBSession.query(Image).filter(Image.filename == image['filename'])
    if updating:
        sql = sql.filter(Image.document_id != image['document_id'])
    if sql.count() > 0:
        request.errors.add('body', 'filename', 'Unique')


def make_validator_filename_unique(updating):
    if updating:

        def f(request, **kwargs):
            image = request.validated
            check_filename_unique(image, request, updating=True)
    else:

        def f(request, **kwargs):
            image = request.validated
            check_filename_unique(image, request, updating=False)

    return f


base_validate_image_create = make_validator_create(fields_image.get('required'))
base_validate_image_update = make_validator_update(fields_image.get('required'))
validate_filename_create = make_validator_filename_unique(updating=False)
validate_filename_update = make_validator_filename_unique(updating=True)


def validate_image_create(request, **kwargs):
    base_validate_image_create(request, **kwargs)
    validate_filename_create(request, **kwargs)


def validate_image_update(request, **kwargs):
    base_validate_image_update(request, **kwargs)
    validate_filename_update(request, **kwargs)


validate_associations_create = functools.partial(
    validate_associations, IMAGE_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, IMAGE_TYPE, False
)


def validate_list_image_create(request, **kwargs):
    if not request.validated.get('images'):
        return

    for image in request.validated['images']:
        validate_document(image, request, fields_image.get('required'), updating=False)
        check_filename_unique(image, request, updating=False)


def validate_list_associations_create(request, **kwargs):
    if not request.validated.get('images'):
        return

    for document in request.validated['images']:
        associations_in = document.get('associations', None)
        if not associations_in:
            continue
        document['associations'] = validate_associations_in(
            associations_in, IMAGE_TYPE, request.errors
        )


def create_image(self, document_in):
    document = self._create_document(document_in, image_schema)
    publish_image_in_backend(self.request, document.filename)

    return document


def before_image_update(request, document, document_in):
    """Check filename updates and publish them on the image backend.

    Callback sent to DocumentRest.update_document()
    check update of filename, and publish on image backend if needed.
    """
    old_filename = document.filename
    new_filename = document_in.filename

    if old_filename != new_filename:
        publish_image_in_backend(request, new_filename)


def image_backend_endpoint(settings, action):
    """Build the URL of an image backend endpoint.

    A trailing slash in `image_backend.url` must not produce a `//` path,
    which the image backend answers with a 404.
    """
    return '{}/{}'.format(settings['image_backend.url'].rstrip('/'), action)


def publish_image_in_backend(request, filename):
    settings = request.registry.settings
    url = image_backend_endpoint(settings, 'publish')
    data = {'secret': settings['image_backend.secret_key'], 'filename': filename}

    response = requests.post(url, data, timeout=int(settings['url.timeout']))

    if response.status_code != 200:
        raise HTTPInternalServerError(
            f'Image backend returns : {response.status_code} {response.reason}'
        )


def delete_all_files_for_image(document_id, request):
    """Delete the files of an image document after commit.

    When the current database transaction is committed successfully,
    delete all files of the given image document by making a request to
    the image service.
    Note that no error is raised if this requests fails.
    """
    filenames_result = (
        DBSession.query(ArchiveImage.filename)
        .filter(ArchiveImage.document_id == document_id)
        .group_by(ArchiveImage.filename)
        .all()
    )
    filenames = [f for (f,) in filenames_result]

    settings = request.registry.settings
    url = image_backend_endpoint(settings, 'delete')

    def send_delete_request():
        response = requests.post(
            url,
            data={
                'secret': settings['image_backend.secret_key'],
                'filenames': filenames,
            },
            timeout=int(settings['url.timeout']),
        )

        if response.status_code != 200:
            raise HTTPInternalServerError(
                f'Deleting image files failed: {response.status_code} {response.reason}'
            )

    run_on_successful_transaction(send_delete_request)


@resource(collection_path='/images', path='/images/{id}')
class ImageRest(DocumentRest):
    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(IMAGE_TYPE, image_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            image_documents_config, image_schema, set_custom_fields=set_creator
        )

    @restricted_json_view(
        validators=[
            body_validator(ImageCreateSchema),
            validate_image_create,
            validate_associations_create,
        ],
    )
    def collection_post(self):
        document_in = self.request.validated
        document = create_image(self, document_in)
        return {'document_id': document.document_id}

    @restricted_json_view(
        validators=[
            body_validator(ImageUpdateSchema),
            validate_id,
            validate_image_update,
            validate_associations_update,
        ],
    )
    def put(self):
        if not self.request.has_permission('moderator'):
            image_id = self.request.validated['id']
            image = DBSession.get(Image, image_id)
            if image is None:
                raise HTTPNotFound(f'No image found for id {image_id}')
            new_image_type = self.request.validated['document']['image_type']
            if new_image_type == 'copyright':
                if new_image_type != image.image_type:
                    raise HTTPForbidden('No permission to change to copyright type')
            elif image.image_type == 'collaborative':
                if new_image_type != image.image_type:
                    raise HTTPBadRequest(
                        'Image type cannot be changed for collaborative images'
                    )
            # personal images should only be modifiable by
            # their creator and moderators
            elif not has_been_created_by(image_id, self.request.authenticated_userid):
                raise HTTPForbidden('No permission to change this image')
        return self._put(
            Image,
            image_schema,
            before_update=functools.partial(before_image_update, self.request),
        )


# only `collection_post`: it posts a list of images
@resource(collection_path='/images/list', path='/images/list/{id}')
class ImageListRest(DocumentRest):
    @restricted_json_view(
        validators=[
            body_validator(ImageListCreateSchema),
            validate_list_image_create,
            validate_list_associations_create,
        ],
    )
    def collection_post(self):
        images_in = self.request.validated['images']

        image_ids = []
        images = []
        for document_in in images_in:
            document = create_image(self, document_in)
            images.append(document)
            image_ids.append({'document_id': document.document_id})

        update_feed_images_upload(images, images_in, self.request.authenticated_userid)

        return {'images': image_ids}


@resource(path='/images/{id}/{lang}/info')
class ImageInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(image_documents_config)


def validate_size(request, **kwargs):
    """Check if size is one of the available sizes."""
    size = request.GET.get('size', None)
    if size in (None, 'SI', 'MI', 'BI'):
        request.validated['size'] = size
    else:
        request.errors.add('querystring', 'size', 'invalid size')


def validate_extension(request, **kwargs):
    """Check if the extension is an modern one."""
    ext = request.GET.get('extension', None)
    size = request.GET.get('size', None)
    if (ext is None) or (ext in ('webp', 'avif') and size is not None):
        request.validated['extension'] = ext
    else:
        request.errors.add('querystring', 'extension', 'invalid extension')


@resource(path='/images/proxy/{id}')
class ImageProxyRest(ACLDefault):
    @view(validators=[validate_id, validate_size, validate_extension])
    def get(self):
        document_id = self.request.validated['id']
        size = self.request.validated['size']
        extension = self.request.validated['extension']
        # follows merged images to their target, whose files still exist
        filename = get_image_filenames([document_id]).get(document_id)
        if filename is None:
            raise HTTPNotFound()
        image_url = self.request.registry.settings['image_url']
        if size is None:
            location = f'{image_url}{filename}'
        else:
            base, ext = os.path.splitext(filename)
            if extension is None:
                ext = '.jpg' if ext == '.svg' else ext
            else:
                ext = '.' + extension
            location = f'{image_url}{base}{size}{ext}'
        return HTTPFound(location, headers={'Cache-Control': PROXY_CACHE_CONTROL})


def set_creator(image):
    """Set the creator (the user who created an image) on an image."""
    set_creator_on_documents([image], 'creator')


@resource(path='/images/{id}/{lang}/{version_id}')
class ImageVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveImage, IMAGE_TYPE, ArchiveDocumentLocale, image_schema
        )
