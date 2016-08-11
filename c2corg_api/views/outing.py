import functools
from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import ArchiveDocument, DocumentGeometry
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale, OUTING_TYPE
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.user import User
from c2corg_api.models.utils import get_mid_point
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations
from c2corg_common.attributes import activities
from c2corg_common.fields_outing import fields_outing
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPForbidden
from sqlalchemy.sql.expression import exists, and_, over
from sqlalchemy.sql.functions import func

validate_outing_create = make_validator_create(
    fields_outing, 'activities', activities)
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, OUTING_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, OUTING_TYPE, False)


def validate_required_associations(request):
    missing_user = False
    missing_route = False

    associations = request.validated.get('associations', None)
    if not associations:
        missing_user = True
        missing_route = True
    else:
        linked_routes = associations.get('routes', [])
        if not linked_routes:
            missing_route = True

        linked_users = associations.get('users', [])
        if not linked_users:
            missing_user = True

    if missing_user:
        request.errors.add(
            'body', 'associations.users', 'at least one user required')

    if missing_route:
        request.errors.add(
            'body', 'associations.routes', 'at least one route required')


def adapt_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_outing, activities, field_list_type)
    return restrict_schema(schema_outing, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'listing')


@resource(collection_path='/outings', path='/outings/{id}',
          cors_policy=cors_policy)
class OutingRest(DocumentRest):

    @view(validators=[
        validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            Outing, schema_outing, OUTING_TYPE,
            adapt_schema=listing_schema_adaptor, set_custom_fields=set_author)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(
            Outing, schema_outing, adapt_schema=schema_adaptor)

    @restricted_json_view(schema=schema_create_outing,
                          validators=[validate_outing_create,
                                      validate_associations_create,
                                      validate_required_associations])
    def collection_post(self):
        set_default_geom = functools.partial(
            set_default_geometry,
            self.request.validated['associations']['routes']
        )
        return self._collection_post(
            schema_outing, before_add=set_default_geom)

    @restricted_json_view(schema=schema_update_outing,
                          validators=[validate_id,
                                      validate_outing_update,
                                      validate_associations_update,
                                      validate_required_associations])
    def put(self):
        if not self.request.has_permission('moderator'):
            # moderators can change every outing
            if not self._has_permission(
                    self.request.authenticated_userid,
                    self.request.validated['id']):
                # but a normal user can only change an outing that they are
                # associated to
                raise HTTPForbidden('No permission to change this outing')
        return self._put(
            Outing, schema_outing, before_update=update_default_geometry)

    def _has_permission(self, user_id, outing_id):
        """Check if the user with the given id has permission to change an
        outing. That is only users that are currently assigned to the outing
        can modify it.
        """
        return DBSession.query(exists().where(
            and_(
                Association.parent_document_id == user_id,
                Association.child_document_id == outing_id
            ))).scalar()


def set_author(outings, lang):
    """Set the author (the user who created an outing) on a list of
    outings.
    """
    if not outings:
        return
    outing_ids = [o.document_id for o in outings]

    t = DBSession.query(
        ArchiveDocument.document_id.label('document_id'),
        User.id.label('user_id'),
        User.username.label('username'),
        User.name.label('name'),
        over(
            func.rank(), partition_by=ArchiveDocument.document_id,
            order_by=HistoryMetaData.id).label('rank')). \
        select_from(ArchiveDocument). \
        join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1)). \
        join(HistoryMetaData,
             DocumentVersion.history_metadata_id == HistoryMetaData.id). \
        join(User,
             HistoryMetaData.user_id == User.id). \
        filter(ArchiveDocument.document_id.in_(outing_ids)). \
        subquery('t')
    query = DBSession.query(
            t.c.document_id, t.c.user_id, t.c.username, t.c.name). \
        filter(t.c.rank == 1)

    author_for_outings = {
        document_id: {
            'username': username,
            'name': name,
            'user_id': user_id
        } for document_id, user_id, username, name in query
    }

    for outing in outings:
        outing.author = author_for_outings.get(outing.document_id)


def set_default_geometry(linked_routes, outing, user_id):
    """When creating a new outing, set the default geometry to the middle point
    of a given track, if not to the geometry of an associated route.
    """
    if outing.geometry is not None and outing.geometry.geom is not None:
        # default geometry already set
        return

    if outing.geometry is not None and outing.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)
    elif linked_routes:
        route_id = linked_routes[0]['document_id']
        # get default point from route
        route_point = DBSession.query(DocumentGeometry.geom).filter(
            DocumentGeometry.document_id == route_id).scalar()
        if route_point is not None:
            outing.geometry = DocumentGeometry(geom=route_point)


def update_default_geometry(outing, outing_in, user_id):
    """When updating an outing, set the default geometry to the middle point
    of a new track, or directly update with a given geometry.
    """
    # TODO also use geometry of main waypoint when main waypoint has changed?
    geometry_in = outing_in.geometry
    if geometry_in is not None and geometry_in.geom is not None:
        # default geom is manually set in the request
        return
    elif geometry_in is not None and geometry_in.geom_detail is not None:
        # update the default geom with the new track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, ArchiveOutingLocale, schema_outing, schema_adaptor)
