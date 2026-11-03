import functools

from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.models.area import (
    AREA_TYPE,
    ArchiveArea,
    Area,
)
from c2corg_api.models.area_association import update_area as associate_area
from c2corg_api.models.cache_version import update_cache_version_for_area
from c2corg_api.models.common.fields_area import fields_area
from c2corg_api.models.document import ArchiveDocumentLocale, UpdateType
from c2corg_api.schemas.area import AreaCreateSchema, AreaUpdateSchema, area_schema
from c2corg_api.schemas.base import body_validator
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document import (
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import area_documents_config
from c2corg_api.views.document_version import document_version
from c2corg_api.views.resource import view
from c2corg_api.views.validation import (
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

validate_area_create = make_validator_create(fields_area.get('required'))
validate_area_update = make_validator_update(fields_area.get('required'))
validate_associations_create = functools.partial(validate_associations, AREA_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, AREA_TYPE, False
)


@restricted_json_view(
    validators=[
        body_validator(AreaCreateSchema),
        validate_area_create,
        validate_associations_create,
    ],
    permission='moderator',
)
def create_area(request):
    return create_document(request, area_schema, after_add=insert_associations)


create_area.view_name = 'AreaRest.collection_post'


@restricted_json_view(
    validators=[
        body_validator(AreaUpdateSchema),
        validate_id,
        validate_area_update,
        validate_associations_update,
    ],
)
def update_area(request):
    if not request.has_permission('moderator'):
        # the geometry of areas should not be modifiable for non-moderators
        if request.validated['document'] and request.validated['document']['geometry']:
            raise HTTPBadRequest('No permission to change the geometry')

    return put_document(request, Area, area_schema, after_update=update_associations)


update_area.view_name = 'AreaRest.put'


@view(validators=[validate_pagination, validate_preferred_lang_param])
def list_areas(request):
    return collection_get(request, AREA_TYPE, area_documents_config)


list_areas.view_name = 'AreaRest.collection_get'


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_area(request):
    return read_document(
        request, area_documents_config, area_schema, include_areas=False
    )


get_area.view_name = 'AreaRest.get'


@view(validators=[validate_id, validate_lang])
def get_area_info(request):
    return document_info(request, area_documents_config)


get_area_info.view_name = 'AreaInfoRest.get'


def insert_associations(area, user_id):
    """Create links between this new area and documents."""
    associate_area(area, reset=False)


def update_associations(area, update_types, user_id):
    """Update the links between this area and documents.

    Update the links between this area and documents when the geometry
    has changed.
    """
    if update_types:
        # update cache key for currently associated docs
        update_cache_version_for_area(area)

    if UpdateType.GEOM in update_types:
        associate_area(area, reset=True)


@view(validators=[validate_id, validate_lang, validate_version_id])
def get_area_version(request):
    return document_version(
        request, ArchiveArea, AREA_TYPE, ArchiveDocumentLocale, area_schema
    )


get_area_version.view_name = 'AreaVersionRest.get'
