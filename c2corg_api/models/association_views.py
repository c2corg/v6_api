from c2corg_api.ext import sqa_view
from c2corg_api.models import Base, schema
from c2corg_api.models.association import Association
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import and_, union, select, text, join
from sqlalchemy.sql.functions import func
from sqlalchemy import Integer


def _get_select_waypoints_for_routes():
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

    return union(
            select_linked_waypoints.select(),
            select_waypoint_parents.select(),
            select_waypoint_grandparents.select()
        ). \
        cte('all_waypoints')


def _get_select_waypoints_for_routes_aggregated():
    """ Returns a select which retrieves for every route the ids for the
    waypoints that are associated to the route. It also returns the parent
    and grand-parent of waypoints, so that when searching for routes for a
    waypoint, you also get the routes associated to child waypoints.

    E.g. when searching for routes for Calanques, you also get the routes
    associated to sub-sectors.
    """
    all_waypoints = _get_select_waypoints_for_routes()
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
        _get_select_waypoints_for_routes_aggregated())


Route.associated_waypoints_ids = relationship(
    WaypointsForRoutesView,
    uselist=False,
    primaryjoin=Route.document_id == WaypointsForRoutesView.route_id,
    foreign_keys=WaypointsForRoutesView.route_id,
    viewonly=True, cascade='expunge'
)


def _get_select_waypoints_for_outings_aggregated():
    """ Returns a select which retrieves for every outing the ids for the
    waypoints that are associated to routes associated to the outing. It
    also returns the parent and grand-parent of waypoints, so that when
    searching for outings for a waypoint, you also get the outings associated
    to child waypoints.

    E.g. when searching for outings in Calanques, you also get the outings
    associated to sub-sectors.
    """
    outing_type = text('\'' + OUTING_TYPE + '\'')
    route_type = text('\'' + ROUTE_TYPE + '\'')
    all_waypoints_for_routes = _get_select_waypoints_for_routes()
    waypoints_for_outings = \
        select([
            Association.child_document_id.label('outing_id'),
            all_waypoints_for_routes.c.waypoint_id
        ]). \
        select_from(join(
            Association,
            all_waypoints_for_routes,
            and_(
                Association.parent_document_id ==
                all_waypoints_for_routes.c.route_id,
                Association.parent_document_type == route_type,
                Association.child_document_type == outing_type
            ))). \
        cte('waypoints_for_outings')
    return \
        select([
            waypoints_for_outings.c.outing_id.label('outing_id'),
            func.array_agg(
                waypoints_for_outings.c.waypoint_id,
                type_=postgresql.ARRAY(Integer)).label('waypoint_ids')
        ]). \
        select_from(waypoints_for_outings). \
        group_by(waypoints_for_outings.c.outing_id)


class WaypointsForOutingsView(Base):
    """ A (non-materialized) view which contains the associated waypoints
     for each outing. This view is used when filling the search index for
     outings.
    """
    __table__ = sqa_view.view(
        'waypoints_for_outings',
        schema,
        Base.metadata,
        _get_select_waypoints_for_outings_aggregated())


Outing.associated_waypoints_ids = relationship(
    WaypointsForOutingsView,
    uselist=False,
    primaryjoin=Outing.document_id == WaypointsForOutingsView.outing_id,
    foreign_keys=WaypointsForOutingsView.outing_id,
    viewonly=True, cascade='expunge'
)
