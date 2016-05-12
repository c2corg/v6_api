from c2corg_api.models import DBSession
from c2corg_api.models.document import Document
from c2corg_api.models.route import Route
from c2corg_common.associations import valid_associations
from cornice.resource import resource
from pyramid.httpexceptions import HTTPBadRequest

from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.models.association import schema_association, \
    Association, exists_already
from sqlalchemy.sql.expression import exists


def validate_association(request):
    """Check if the given documents exist and if an association between the
    two document types is valid.
    """
    parent_document_id = request.validated.get('parent_document_id')
    child_document_id = request.validated.get('child_document_id')

    parent_document_type = None
    if parent_document_id:
        parent_document_type = DBSession.query(Document.type). \
            filter(Document.document_id == parent_document_id).scalar()
        if not parent_document_type:
            request.errors.add(
                'body', 'parent_document_id', 'parent document does not exist')

    child_document_type = None
    if child_document_id:
        child_document_type = DBSession.query(Document.type). \
            filter(Document.document_id == child_document_id).scalar()
        if not child_document_type:
            request.errors.add(
                'body', 'child_document_id', 'child document does not exist')

    if parent_document_type and child_document_type:
        association_type = (parent_document_type, child_document_type)
        if association_type not in valid_associations:
            request.errors.add(
                'body', 'association', 'invalid association type')


@resource(collection_path='/associations', path='/associations/{id}',
          cors_policy=cors_policy)
class AssociationRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        schema=schema_association, validators=[validate_association])
    def collection_post(self):
        association = schema_association.objectify(self.request.validated)

        if exists_already(association):
            raise HTTPBadRequest(
                'association (or its back-link) exists already')

        DBSession.add(association)
        DBSession.add(
            association.get_log(self.request.authenticated_userid))

        return {}

    @restricted_json_view(schema=schema_association)
    def collection_delete(self):
        association_in = schema_association.objectify(self.request.validated)

        association = self._load(association_in)
        if association is None:
            # also accept {parent_document_id: y, child_document_id: x} when
            # for an association {parent_document_id: x, child_document_id: x}
            association_in = Association(
                parent_document_id=association_in.child_document_id,
                child_document_id=association_in.parent_document_id)
            association = self._load(association_in)
            if association is None:
                raise HTTPBadRequest('association does not exist')

        if is_main_waypoint_association(association):
            raise HTTPBadRequest(
                'as the main waypoint of the route, this waypoint can not '
                'be disassociated')

        log = association.get_log(
            self.request.authenticated_userid, is_creation=False)

        DBSession.delete(association)
        DBSession.add(log)

        return {}

    def _load(self, association_in):
        return DBSession.query(Association). \
            get((association_in.parent_document_id,
                 association_in.child_document_id))


def is_main_waypoint_association(association):
    return DBSession.query(
        exists().
        where(Route.document_id == association.child_document_id).
        where(Route.main_waypoint_id == association.parent_document_id)
    ).scalar()
