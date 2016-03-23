from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.views import set_best_locale
from colanderalchemy.schema import SQLAlchemySchemaNode
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    DateTime,
    ForeignKey
    )
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.orm import relationship, joinedload, load_only
import datetime

from c2corg_api.models import Base, schema, users_schema, DBSession
from c2corg_api.models.document import Document
from sqlalchemy.sql.expression import or_, and_


class Association(Base):
    """Associations between documents.

    Certain associations build a hierarchy between the documents (e.g. between
    summits), in this case it's important which document is the "parent" and
    which is the "child" of the association. For other undirected associations
    it doesn't matter which document is the "parent" or "child".
    """
    __tablename__ = 'associations'

    parent_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    parent_document = relationship(
        Document, primaryjoin=parent_document_id == Document.document_id)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)

    __table_args__ = (
        PrimaryKeyConstraint(parent_document_id, child_document_id),
        Base.__table_args__
    )


class AssociationLog(Base):
    """Model to log when an association between documents was established or
    removed.
    """
    __tablename__ = 'association_log'

    id = Column(Integer, primary_key=True)

    parent_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    parent_document = relationship(
        Document, primaryjoin=parent_document_id == Document.document_id)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)

    is_creation = Column(Boolean, default=True, nullable=False)
    written_at = Column(
        DateTime, default=datetime.datetime.now, nullable=False)

schema_association = SQLAlchemySchemaNode(
    Association,
    # whitelisted attributes
    includes=['parent_document_id', 'child_document_id'],
    overrides={})


def get_associations(document, lang):
    """Load and return associated documents.
    """
    def limit_waypoint_fields(query):
        return query. \
            options(load_only(
                Waypoint.waypoint_type, Waypoint.document_id,
                Waypoint.elevation, Waypoint.version)). \
            options(joinedload(Waypoint.locales).load_only(
                WaypointLocale.lang, WaypointLocale.title,
                WaypointLocale.version))

    parent_waypoints = limit_waypoint_fields(
        DBSession.query(Waypoint).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             Association.parent_document_id == Waypoint.document_id).
        filter(Association.child_document_id == document.document_id)). \
        all()
    child_waypoints = limit_waypoint_fields(
        DBSession.query(Waypoint).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             Association.child_document_id == Waypoint.document_id).
        filter(Association.parent_document_id == document.document_id)). \
        all()

    def limit_route_fields(query):
        return query.\
            options(load_only(
                Route.document_id, Route.activities, Route.elevation_min,
                Route.elevation_max, Route.version)). \
            options(joinedload(Waypoint.locales).load_only(
                RouteLocale.lang, RouteLocale.title, RouteLocale.title_prefix,
                RouteLocale.version))

    routes = limit_route_fields(
        DBSession.query(Route).
        filter(Route.redirects_to.is_(None)).
        join(
            Association,
            or_(
                and_(
                    Association.child_document_id == Route.document_id,
                    Association.parent_document_id == document.document_id),
                and_(
                    Association.child_document_id == document.document_id,
                    Association.parent_document_id == Route.document_id)))). \
        all()

    if lang is not None:
        set_best_locale(parent_waypoints, lang)
        set_best_locale(child_waypoints, lang)
        set_best_locale(routes, lang)

    return parent_waypoints + child_waypoints, routes
