from c2corg_api.models import DBSession
from c2corg_api.models.document import Document
from c2corg_common.associations import valid_associations
from cornice.resource import resource
from pyramid.httpexceptions import HTTPBadRequest

from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.models.association import schema_association, \
    AssociationLog, Association
from sqlalchemy.sql.expression import or_, and_


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

        if self._exists_already(association):
            raise HTTPBadRequest(
                'association (or its back-link) exists already')

        DBSession.add(association)
        DBSession.add(
            self._get_log(association, self.request.authenticated_userid))

        return {}

    @restricted_json_view(schema=schema_association)
    def collection_delete(self):
        association_in = schema_association.objectify(self.request.validated)

        association = self._load(association_in)
        if association is None:
            raise HTTPBadRequest('association does not exist')

        log = self._get_log(
            association, self.request.authenticated_userid, is_creation=False)

        DBSession.delete(association)
        DBSession.add(log)

        return {}

    def _get_log(self, association, user_id, is_creation=True):
        return AssociationLog(
            parent_document_id=association.parent_document_id,
            child_document_id=association.child_document_id,
            user_id=user_id,
            is_creation=is_creation
        )

    def _exists_already(self, link):
        """ Checks if the given association exists already. For example, for
        two given documents D1 and D2, it checks if there is no association
        D1 -> D2 or D2 -> D1.
        """
        associations_exists = DBSession.query(Association). \
            filter(or_(
                and_(
                    Association.parent_document_id == link.parent_document_id,
                    Association.child_document_id == link.child_document_id
                ),
                and_(
                    Association.child_document_id == link.parent_document_id,
                    Association.parent_document_id == link.child_document_id
                )
            )). \
            exists()
        return DBSession.query(associations_exists).scalar()

    def _load(self, association_in):
        return DBSession.query(Association). \
            get((association_in.parent_document_id,
                 association_in.child_document_id))
