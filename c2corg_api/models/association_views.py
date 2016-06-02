from c2corg_api.ext import sqa_view
from c2corg_api.models import Base, schema
from c2corg_api.models.association import Association
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import and_, union, select, text, join
from sqlalchemy.sql.functions import func
from sqlalchemy import Integer


def _get_select_waypoints_for_routes():
    """ Returns a select which retrieves for every route the ids for the
    waypoints that are associated to the route. It also returns the parent
    and grand-parent of waypoints, so that when searching for routes for a
    waypoint, you also get the routes associated to child waypoints.

    E.g. when searching for routes for Calanques, you also get the routes
    associated to sub-sectors.
    """
    waypoint_type = text('\'' + WAYPOINT_TYPE + '\'')
    route_type = text('\'' + ROUTE_TYPE + '\'')

    select_linked_waypoints = \
        select([
            Association.child_document_id.label('route_id'),
            Association.parent_document_id.label('waypoint_id')
        ]). \
        where(
            and_(
                Association.parent_document_type == waypoint_type,
                Association.child_document_type == route_type)). \
        cte('linked_waypoints')

    select_waypoint_parents = \
        select([
            select_linked_waypoints.c.route_id,
            Association.parent_document_id.label('waypoint_id')
        ]). \
        select_from(join(
            select_linked_waypoints,
            Association,
            and_(
                Association.child_document_id ==
                select_linked_waypoints.c.waypoint_id,
                Association.parent_document_type == waypoint_type
            ))). \
        cte('waypoint_parents')

    select_waypoint_grandparents = \
        select([
            select_waypoint_parents.c.route_id,
            Association.parent_document_id.label('waypoint_id')
        ]). \
        select_from(join(
            select_waypoint_parents,
            Association,
            and_(
                Association.child_document_id ==
                select_waypoint_parents.c.waypoint_id,
                Association.parent_document_type == waypoint_type
            ))). \
        cte('waypoint_grandparents')

    all_waypoints = union(
            select_linked_waypoints.select(),
            select_waypoint_parents.select(),
            select_waypoint_grandparents.select()
        ). \
        cte('all_waypoints')

    return \
        select([
            all_waypoints.c.route_id.label('route_id'),
            func.array_agg(
                all_waypoints.c.waypoint_id,
                type_=postgresql.ARRAY(Integer)).label('waypoint_ids')
        ]). \
        select_from(all_waypoints). \
        group_by(all_waypoints.c.route_id)


class WaypointsForRoutesView(Base):
    """ A (non-materialized) view which contains the associated waypoints
     for each route. This view is used when filling the search index for
     routes.
    """
    __table__ = sqa_view.view(
        'waypoints_for_routes',
        schema,
        Base.metadata,
        _get_select_waypoints_for_routes())


Route.associated_waypoints_ids = relationship(
    WaypointsForRoutesView,
    uselist=False,
    primaryjoin=Route.document_id == WaypointsForRoutesView.route_id,
    foreign_keys=WaypointsForRoutesView.route_id,
    viewonly=True, cascade='expunge'
)
