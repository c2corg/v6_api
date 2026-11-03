import functools

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models.common.fields_xreport import fields_xreport
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    ArchiveXreport,
    ArchiveXreportLocale,
    Xreport,
    XreportLocale,
)
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.xreport import (
    XreportCreateSchema,
    XreportUpdateSchema,
    xreport_schema,
    xreport_without_personal_schema,
)
from c2corg_api.views import restricted_json_view, set_private_cache_header
from c2corg_api.views import set_creator as set_creator_on_documents
from c2corg_api.views.document import (
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import xreport_documents_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.resource import resource, view
from c2corg_api.views.validation import (
    is_associated_user,
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

validate_xreport_create = make_validator_create(fields_xreport.get('required'))
validate_xreport_update = make_validator_update(fields_xreport.get('required'))
validate_associations_create = functools.partial(
    validate_associations, XREPORT_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, XREPORT_TYPE, False
)


@restricted_json_view(
    validators=[
        body_validator(XreportCreateSchema),
        validate_xreport_create,
        validate_associations_create,
    ],
)
def create_xreport(request):
    return create_document(request, xreport_schema, allow_anonymous=True)


create_xreport.view_name = 'XreportRest.collection_post'


@restricted_json_view(
    validators=[
        body_validator(XreportUpdateSchema),
        validate_id,
        validate_xreport_update,
        validate_associations_update,
    ],
)
def update_xreport(request):
    if not _has_permission(request, request.validated['id']):
        raise HTTPForbidden('No permission to change this xreport')

    return put_document(request, Xreport, xreport_schema)


update_xreport.view_name = 'XreportRest.put'


@view(validators=[validate_pagination, validate_preferred_lang_param])
def list_xreports(request):
    return collection_get(request, XREPORT_TYPE, xreport_documents_config)


list_xreports.view_name = 'XreportRest.collection_get'


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_xreport(request):
    set_private_cache_header(request)
    if not _has_permission(request, request.validated['id']):
        # only moderators and the author of a xreport can access the full
        # xreport (including personal information)
        return read_document(
            request,
            xreport_documents_config,
            xreport_without_personal_schema,
            clazz_locale=XreportLocale,
            set_custom_fields=set_author,
        )

    return read_document(
        request,
        xreport_documents_config,
        xreport_schema,
        clazz_locale=XreportLocale,
        custom_cache_key='private',
        set_custom_fields=set_author,
    )


get_xreport.view_name = 'XreportRest.get'


def _has_permission(request, xreport_id):
    """Check if the user may see or change the non-public xreport data.

    Check if the authenticated user has permission to view non-public
    information of the xreport or th change the xreport. That is only
    moderators and users that are currently assigned to the xreport
    can modify it.
    """
    if request.authorization is None:
        return False

    if request.has_permission('moderator'):
        return True

    if has_been_created_by(xreport_id, request.authenticated_userid):
        return True

    if is_associated_user(xreport_id, request.authenticated_userid):
        return True

    return False


@resource(path='/xreports/{id}/{lang}/{version_id}')
class XreportVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveXreport,
            XREPORT_TYPE,
            ArchiveXreportLocale,
            xreport_without_personal_schema,
        )


@resource(path='/xreports/{id}/{lang}/info')
class XreportInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(xreport_documents_config)


def set_author(xreport):
    """Set the creator (the user who is an author) of the report."""
    set_creator_on_documents([xreport], 'author')
