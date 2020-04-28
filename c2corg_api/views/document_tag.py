import logging

from c2corg_api import DBSession
from c2corg_api.models.document import Document
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import create_int_validator
from colander import MappingSchema, SchemaNode, Integer, required
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest

log = logging.getLogger(__name__)


class DocumentTagSchema(MappingSchema):
    document_id = SchemaNode(Integer(), missing=required)


def get_tag_relation(user_id, document_id):
    return DBSession. \
        query(DocumentTag). \
        filter(DocumentTag.user_id == user_id). \
        filter(DocumentTag.document_id == document_id). \
        first()

validate_document_id = create_int_validator('document_id')


def validate_document(request, **kwargs):
    """ Check that the document exists.
    """
    document_id = request.validated['document_id']
    document_exists_query = DBSession.query(Document). \
        filter(Document.document_id == document_id). \
        exists()
    document_exists = DBSession.query(document_exists_query).scalar()

    if not document_exists:
        request.errors.add(
            'body', 'document_id',
            'document {0} does not exist'.format(document_id))


@resource(path='/tags/add', cors_policy=cors_policy)
class DocumentTagRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        schema=DocumentTagSchema(),
        validators=[colander_body_validator, validate_document])
    def post(self):
        """ Tag the given document as todo.
        Creates a tag relation, so that the authenticated user is
        marking the given document as todo.


        Request:
            `POST` `/tags/add`

        Request body:
            {'document_id': @document_id@}

        """
        document_id = self.request.validated['document_id']
        document_type = ROUTE_TYPE
        user_id = self.request.authenticated_userid

        if get_tag_relation(user_id, document_id):
            raise HTTPBadRequest('This document is already tagged.')

        DBSession.add(DocumentTag(
            user_id=user_id, document_id=document_id,
            document_type=document_type))
        DBSession.add(DocumentTagLog(
            user_id=user_id, document_id=document_id,
            document_type=document_type, is_creation=True))

        notify_es_syncer(self.request.registry.queue_config)

        return {}


@resource(path='/tags/remove', cors_policy=cors_policy)
class DocumentUntagRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        schema=DocumentTagSchema(),
        validators=[colander_body_validator, validate_document])
    def post(self):
        """ Untag the given document.

        Request:
            `POST` `/tags/remove`

        Request body:
            {'document_id': @document_id@}

        """
        document_id = self.request.validated['document_id']
        document_type = ROUTE_TYPE
        user_id = self.request.authenticated_userid
        tag_relation = get_tag_relation(user_id, document_id)

        if tag_relation:
            DBSession.delete(tag_relation)
            DBSession.add(DocumentTagLog(
                user_id=user_id, document_id=document_id,
                document_type=document_type, is_creation=False))
        else:
            log.warn(
                'tried to delete not existing tag relation '
                '({0}, {1})'.format(user_id, document_id))
            raise HTTPBadRequest('This document has no such tag.')

        notify_es_syncer(self.request.registry.queue_config)

        return {}


@resource(path='/tags/has/{document_id}', cors_policy=cors_policy)
class DocumentTaggedRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(validators=[validate_document_id])
    def get(self):
        """ Check if the authenticated user has tagged the given document as todo.

        Request:
            `GET` `tags/has/{document_id}`

        Example response:

            {'todo': true}

        """
        document_id = self.request.validated['document_id']
        user_id = self.request.authenticated_userid
        tag_relation = get_tag_relation(user_id, document_id)

        return {
            'todo': tag_relation is not None
        }
