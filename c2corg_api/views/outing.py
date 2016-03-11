import functools
from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import ArchiveDocument, Document, \
    DocumentGeometry
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.user import User, schema_association_user
from c2corg_api.models.utils import get_mid_point
from c2corg_api.views import cors_policy, restricted_json_view, to_json_dict
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, check_get_for_integer_property
from c2corg_common.attributes import activities
from c2corg_common.fields_outing import fields_outing
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPForbidden
from sqlalchemy.orm import load_only
from sqlalchemy.orm.util import aliased
from sqlalchemy.sql.expression import exists, and_, over
from sqlalchemy.sql.functions import func

validate_outing_create = make_validator_create(
    fields_outing, 'activities', activities, document_field='outing')
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)


def validate_associations(request):
    """Check if the given waypoint and route id are valid.
    """
    route_id = request.validated.get('route_id')
    if route_id:
        route_exists = DBSession.query(
            exists().where(Route.document_id == route_id)).scalar()
        if not route_exists:
            request.errors.add(
                'body', 'route_id', 'route does not exist')

    user_ids = request.validated.get('user_ids')
    if user_ids:
        for user_id in user_ids:
            user_exists = DBSession.query(
                exists().where(User.id == user_id)).scalar()
            if not user_exists:
                request.errors.add(
                    'body', 'user_ids',
                    'user "{0:n}" does not exist'.format(user_id))


def validate_filter_params(request):
    """
    Checks if a given optional waypoint id is an integer,
    if a given optional route id is an integer.
    """
    check_get_for_integer_property(request, 'wp', False)
    check_get_for_integer_property(request, 'r', False)


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
        validate_pagination, validate_preferred_lang_param,
        validate_filter_params])
    def collection_get(self):
        custom_filter = None
        if self.request.validated.get('wp'):
            # only show outings for the given waypoint
            custom_filter = self.filter_on_waypoint(
                self.request.validated['wp'])
        elif self.request.validated.get('r'):
            # only show outings for the given route
            custom_filter = self.filter_on_route(self.request.validated['r'])

        return self._collection_get(
            Outing, schema_outing, listing_schema_adaptor,
            custom_filter=custom_filter, set_custom_fields=set_author)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(
            Outing, schema_outing, schema_adaptor,
            set_custom_associations=OutingRest.set_users)

    @restricted_json_view(schema=schema_create_outing,
                          validators=[validate_outing_create,
                                      validate_associations])
    def collection_post(self):
        create_associations = functools.partial(
            add_associations,
            self.request.validated['route_id'],
            self.request.validated['user_ids']
        )
        set_default_geom = functools.partial(
            set_default_geometry,
            self.request.validated['route_id']
        )
        return self._collection_post(
            schema_outing, document_field='outing',
            before_add=set_default_geom,
            after_add=create_associations)

    @restricted_json_view(schema=schema_update_outing,
                          validators=[validate_id, validate_outing_update])
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

    @staticmethod
    def set_users(outing, lang):
        """Set all linked users on the given outing.
        """
        linked_users = DBSession.query(User). \
            join(Association, Association.parent_document_id == User.id). \
            filter(Association.child_document_id == outing.document_id). \
            options(load_only(User.id, User.username)). \
            all()
        outing.associations['users'] = [
            to_json_dict(user, schema_association_user)
            for user in linked_users
        ]

    def filter_on_route(self, route_id):
        def filter_query(query):
            return query. \
                join(
                    Association,
                    Outing.document_id == Association.child_document_id). \
                filter(Association.parent_document_id == route_id)
        return filter_query

    def filter_on_waypoint(self, waypoint_id):
        def filter_query(query):
            t_outing_route = aliased(Association, name='a1')
            t_route_wp = aliased(Association, name='a2')
            t_route = aliased(Document, name='r')

            return query. \
                join(
                    t_outing_route,
                    Outing.document_id == t_outing_route.child_document_id). \
                join(
                    t_route,
                    and_(
                        t_outing_route.parent_document_id ==
                        t_route.document_id,
                        t_route.type == ROUTE_TYPE)). \
                join(
                    t_route_wp,
                    and_(
                        t_route_wp.parent_document_id == waypoint_id,
                        t_route_wp.child_document_id == t_route.document_id))
        return filter_query


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


def set_default_geometry(route_id, outing):
    """When creating a new outing, set the default geometry to the middle point
    of a given track, if not to the geometry of the associated route.
    """
    if outing.geometry is not None and outing.geometry.geom is not None:
        # default geometry already set
        return

    if outing.geometry is not None and outing.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)
    elif route_id:
        # get default point from route
        route_point = DBSession.query(DocumentGeometry.geom).filter(
            DocumentGeometry.document_id == route_id).scalar()
        if route_point is not None:
            outing.geometry = DocumentGeometry(geom=route_point)


def update_default_geometry(outing, outing_in):
    """When updating an outing, set the default geometry to the middle point
    of a new track, or directly update with a given geometry.
    """
    geometry_in = outing_in.geometry
    if geometry_in is not None and geometry_in.geom is not None:
        # default geom is manually set in the request
        return
    elif geometry_in is not None and geometry_in.geom_detail is not None:
        # update the default geom with the new track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, ArchiveOutingLocale, schema_outing, schema_adaptor)


def add_associations(route_id, user_ids, outing):
    """When creating a new outing, associations to the linked route
    and users are set up at the same time.
    """
    DBSession.add(Association(
        parent_document_id=route_id, child_document_id=outing.document_id))
    for user_id in user_ids:
        DBSession.add(Association(
            parent_document_id=user_id, child_document_id=outing.document_id))
