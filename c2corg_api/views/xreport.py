import functools

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.user import User
from c2corg_api.models.xreport import (
  Xreport,
  schema_xreport,
  schema_create_xreport,
  schema_update_xreport,
  XREPORT_TYPE, ArchiveXreport, ArchiveXreportLocale, XreportLocale,
  schema_xreport_without_personal)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_common.fields_xreport import fields_xreport
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from c2corg_api.views import set_creator as set_creator_on_documents

from c2corg_api.views.document_schemas import xreport_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view, \
    set_private_cache_header
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations, validate_lang, validate_version_id, validate_user_id

from pyramid.httpexceptions import HTTPForbidden

validate_xreport_create = make_validator_create(fields_xreport.get('required'))
validate_xreport_update = make_validator_update(fields_xreport.get('required'))
validate_associations_create = functools.partial(
    validate_associations, XREPORT_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, XREPORT_TYPE, False)

def get_xreports_for_user(request, **kwargs):
    """ Get reports written by the user if he exists.
    """
    user_id = request.validated['u']

    user_exists_query = DBSession.query(User). \
        filter(User.id == user_id). \
        exists()
    user_exists = DBSession.query(user_exists_query).scalar()

    xreports_for_user_info = DBSession.query(
        User.username, User.forum_username,
        Association.child_document_id, Association.child_document_type). \
        filter(User.id == user_id,
               Xreport.document_id == Association.child_document_id,
               Association.parent_document_id == user_id,
               Association.child_document_type == XREPORT_TYPE). \
        all()

    if not user_exists:
        request.errors.add(
            'body', 'user_id', 'user {0} does not exist'.format(user_id))

    # [
    #   {
    #     "child_document_id": 700155,
    #     "child_document_type": "x",
    #     "forum_username": "anakreenskyrider",
    #     "username": "anakreenskyrider"
    #   },
    #   ...
    # ]

    return xreports_for_user_info

    # cant return full documents
    # xreport_ids_list = []
    # # print(xreport_ids_list)  # [700155, 700164, 752525, 770436]
    #
    # for doc in xreports_for_user_info:
    #     # print(doc['child_document_id'])
    #     id = doc['child_document_id']
    #     xreport_ids_list.append(id)
    #
    # xreports_for_user = DBSession.query(Xreport). \
    #     filter(Xreport.document_id.in_(xreport_ids_list)). \
    #     all()
    #
    #
    # # return xreports_for_user
    #
    # # a = get_documents_for_ids(xreport_ids_list)


@resource(path='/xreports-filter', cors_policy=cors_policy)
class XreportFilterRest(DocumentRest):

    # def __init__(self, request):
    #     self.request = request

    @view(validators=[validate_user_id])
    def get(self):
        if self.request.validated['u']:
            return get_xreports_for_user(self.request)


@resource(collection_path='/xreports', path='/xreports/{id}',
          cors_policy=cors_policy)
class XreportRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(XREPORT_TYPE, xreport_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        set_private_cache_header(self.request)
        if not _has_permission(self.request, self.request.validated['id']):
            # only moderators and the author of a xreport can access the full
            # xreport (including personal information)
            return self._get(Xreport, schema_xreport_without_personal,
                             clazz_locale=XreportLocale,
                             set_custom_fields=set_author)

        return self._get(Xreport, schema_xreport,
                         clazz_locale=XreportLocale,
                         custom_cache_key='private',
                         set_custom_fields=set_author)

    @restricted_json_view(
            schema=schema_create_xreport,
            validators=[colander_body_validator,
                        validate_xreport_create,
                        validate_associations_create])
    def collection_post(self):
        return self._collection_post(schema_xreport)

    @restricted_json_view(
            schema=schema_update_xreport,
            validators=[colander_body_validator,
                        validate_id,
                        validate_xreport_update,
                        validate_associations_update])
    def put(self):
        if not _has_permission(self.request, self.request.validated['id']):
            raise HTTPForbidden('No permission to change this xreport')

        return self._put(Xreport, schema_xreport)


def _has_permission(request, xreport_id):
    """Check if the authenticated user has permission to view non-public
    information of the xreport or th change the xreport. That is only
    moderators and users that are currently assigned to the xreport
    can modify it.
    """
    if request.authorization is None:
        return False

    if request.has_permission('moderator'):
        return True

    return has_been_created_by(xreport_id, request.authenticated_userid)


@resource(path='/xreports/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class XreportVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveXreport, ArchiveXreportLocale,
            schema_xreport_without_personal)


@resource(path='/xreports/{id}/{lang}/info', cors_policy=cors_policy)
class XreportInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Xreport)


def set_author(xreport):
    """Set the creator (the user who is an author) of the report.
    """
    set_creator_on_documents([xreport], 'author')
