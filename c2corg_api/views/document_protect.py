import logging

from c2corg_api import DBSession
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document import DocumentRest
from colander import MappingSchema, SchemaNode, Integer, required
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest

log = logging.getLogger(__name__)


class ProtectSchema(MappingSchema):
    document_id = SchemaNode(Integer(), missing=required)


def _get_document(document_id):
    document = DBSession.query(Document).get(document_id)

    if not document:
        raise HTTPBadRequest('Unknown document {}'.format(document_id))

    return document


@resource(path='/documents/protect', cors_policy=cors_policy)
class DocumentProtectRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=ProtectSchema(),
        validators=[colander_body_validator])
    def post(self):
        """ Mark the given document as not editable.

        Request:
            `POST` `/documents/protect`

        Request body:
            {'document_id': @document_id@}

        """
        document_id = self.request.validated['document_id']
        document = _get_document(document_id)

        # Do nothing if document is already protected.
        if document.protected:
            return {}

        document.protected = True

        user_id = self.request.authenticated_userid
        DocumentRest.update_version(
            document, user_id, 'Protected document',
            [UpdateType.FIGURES], [])

        update_cache_version_direct(document_id)

        return {}


@resource(path='/documents/unprotect', cors_policy=cors_policy)
class DocumentUnprotectRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=ProtectSchema(),
        validators=[colander_body_validator])
    def post(self):
        """ Mark the given document as editable.

        Request:
            `POST` `/documents/unprotect`

        Request body:
            {'document_id': @document_id@}

        """
        document_id = self.request.validated['document_id']
        document = _get_document(document_id)

        # Do nothing if document is already not protected.
        if not document.protected:
            return {}

        document.protected = False

        user_id = self.request.authenticated_userid
        DocumentRest.update_version(
            document, user_id, 'Unprotected document',
            [UpdateType.FIGURES], [])

        update_cache_version_direct(document_id)

        return {}
