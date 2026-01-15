from c2corg_api.security.acl import ACLDefault
from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import update_cache_version_associations
from c2corg_api.models.document import Document
from c2corg_api.models.feed import update_feed_association_update
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.es import sync
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.validation import validate_association_permission, \
    check_permission_for_association_removal
from c2corg_api.models.common.associations import valid_associations
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest

from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.models.association import schema_association, \
    Association, exists_already
from sqlalchemy.sql.expression import exists


def validate_association(request, **kwargs):
    """Check if the given documents exist and if an association between the
    two document types is valid.
    """
    parent_document_id = request.validated.get('parent_document_id')
    child_document_id = request.validated.get('child_document_id')

    parent_document_type = None
    if parent_document_id:
        parent_document_type = DBSession.query(Document.type). \
            filter(Document.document_id == parent_document_id). \
            filter(Document.redirects_to.is_(None)).scalar()
        if not parent_document_type:
            request.errors.add(
                'body', 'parent_document_id',
                'parent document does not exist or is redirected')

    child_document_type = None
    if child_document_id:
        child_document_type = DBSession.query(Document.type). \
            filter(Document.document_id == child_document_id). \
            filter(Document.redirects_to.is_(None)).scalar()
        if not child_document_type:
            request.errors.add(
                'body', 'child_document_id',
                'child document does not exist or is redirected')

    if parent_document_type and child_document_type:
        request.validated['parent_document_type'] = parent_document_type
        request.validated['child_document_type'] = child_document_type

        association_type = (parent_document_type, child_document_type)
        if association_type not in valid_associations:
            request.errors.add(
                'body', 'association', 'invalid association type')
        else:
            validate_association_permission(
                request,
                parent_document_id, parent_document_type,
                child_document_id, child_document_type)


@resource(collection_path='/associations', path='/associations/{id}',
          cors_policy=cors_policy)
class AssociationRest(ACLDefault):

    @restricted_json_view(
        schema=schema_association,
        validators=[colander_body_validator, validate_association])
    def collection_post(self):
        association = schema_association.objectify(self.request.validated)
        association.parent_document_type = \
            self.request.validated['parent_document_type']
        association.child_document_type = \
            self.request.validated['child_document_type']

        if exists_already(association):
            raise HTTPBadRequest(
                'association (or its back-link) exists already')

        DBSession.add(association)
        DBSession.add(
            association.get_log(self.request.authenticated_userid))

        update_cache_version_associations(
            [{'parent_id': association.parent_document_id,
              'parent_type': association.parent_document_type,
              'child_id': association.child_document_id,
              'child_type': association.child_document_type}], [])

        notify_es_syncer_if_needed(association, self.request)
        update_feed_association_update(
            association.parent_document_id, association.parent_document_type,
            association.child_document_id, association.child_document_type,
            self.request.authenticated_userid)

        return {}

    @restricted_json_view(
        schema=schema_association, validators=[colander_body_validator])
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

        _check_required_associations(association)
        check_permission_for_association_removal(self.request, association)

        log = association.get_log(
            self.request.authenticated_userid, is_creation=False)

        DBSession.delete(association)
        DBSession.add(log)

        update_cache_version_associations(
            [],
            [{'parent_id': association.parent_document_id,
              'parent_type': association.parent_document_type,
              'child_id': association.child_document_id,
              'child_type': association.child_document_type}])

        notify_es_syncer_if_needed(association, self.request)
        update_feed_association_update(
            association.parent_document_id, association.parent_document_type,
            association.child_document_id, association.child_document_type,
            self.request.authenticated_userid)

        return {}

    def _load(self, association_in):
        return DBSession.query(Association). \
            get((association_in.parent_document_id,
                 association_in.child_document_id))


def _check_required_associations(association):
    if _is_main_waypoint_association(association):
        raise HTTPBadRequest(
            'as the main waypoint of the route, this waypoint can not '
            'be disassociated')
    elif _is_last_waypoint_of_route(association):
        raise HTTPBadRequest(
            'as the last waypoint of the route, this waypoint can not '
            'be disassociated')
    elif _is_last_route_of_outing(association):
        raise HTTPBadRequest(
            'as the last route of the outing, this route can not '
            'be disassociated')


def _is_main_waypoint_association(association):
    return DBSession.query(
        exists().
        where(Route.document_id == association.child_document_id).
        where(Route.main_waypoint_id == association.parent_document_id)
    ).scalar()


def _is_last_waypoint_of_route(association):
    if not (association.parent_document_type == WAYPOINT_TYPE and
            association.child_document_type == ROUTE_TYPE):
        # other association type, nothing to check
        return False

    route_has_other_waypoints = exists(). \
        where(Association.parent_document_type == WAYPOINT_TYPE). \
        where(Association.child_document_type == ROUTE_TYPE). \
        where(Association.parent_document_id !=
              association.parent_document_id). \
        where(
            Association.child_document_id == association.child_document_id)

    return not DBSession.query(route_has_other_waypoints).scalar()


def _is_last_route_of_outing(association):
    if not (association.parent_document_type == ROUTE_TYPE and
            association.child_document_type == OUTING_TYPE):
        # other association type, nothing to check
        return False

    outing_has_other_routes = exists(). \
        where(Association.parent_document_type == ROUTE_TYPE). \
        where(Association.child_document_type == OUTING_TYPE). \
        where(Association.parent_document_id !=
              association.parent_document_id). \
        where(
            Association.child_document_id == association.child_document_id)

    return not DBSession.query(outing_has_other_routes).scalar()


def notify_es_syncer_if_needed(association, request):
    if sync.requires_updates(association):
        notify_es_syncer(request.registry.queue_config)
