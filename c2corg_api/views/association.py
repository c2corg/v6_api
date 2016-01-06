from c2corg_api.models import DBSession
from cornice.resource import resource
from pyramid.httpexceptions import HTTPBadRequest

from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.models.association import schema_association, \
    AssociationLog, Association


@resource(collection_path='/associations', path='/associations/{id}',
          cors_policy=cors_policy)
class AssociationRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(schema=schema_association)
    def collection_post(self):
        association = schema_association.objectify(self.request.validated)

        if self._exists_already(association):
            raise HTTPBadRequest('association exists already')

        # TODO further checks?

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

    def _exists_already(self, association):
        return self._load(association) is not None

    def _load(self, association_in):
        return DBSession.query(Association). \
            get((association_in.parent_document_id,
                 association_in.child_document_id))
