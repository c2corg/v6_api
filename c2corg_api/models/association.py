from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint, WaypointLocale, WAYPOINT_TYPE
from c2corg_api.views import set_best_locale
from c2corg_api.views.validation import updatable_associations, \
    association_keys, association_keys_for_types
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

from c2corg_api.models import Base, schema, users_schema, DBSession
from c2corg_api.models.document import Document
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import or_, and_, union
from sqlalchemy.sql.functions import func


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

    def get_log(self, user_id, is_creation=True):
        return AssociationLog(
            parent_document_id=self.parent_document_id,
            child_document_id=self.child_document_id,
            user_id=user_id,
            is_creation=is_creation
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
    written_at = Column(DateTime, default=func.now(), nullable=False)

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
                Waypoint.elevation, Waypoint.version, Waypoint.protected)). \
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
                Route.elevation_max, Route.version, Route.protected)). \
            options(joinedload(Route.locales.of_type(RouteLocale)).load_only(
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

    return parent_waypoints, child_waypoints, routes


def exists_already(link):
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


def add_association(
        parent_document_id, child_document_id, user_id, check_first=False):
    """Create an association between the two documents and create a log entry
    in the association history table with the given user id.
    """
    association = Association(
        parent_document_id=parent_document_id,
        child_document_id=child_document_id)

    if check_first and exists_already(association):
        return

    DBSession.add(association)
    DBSession.add(association.get_log(user_id, is_creation=True))


def remove_association(
        parent_document_id, child_document_id, user_id, check_first=False):
    """Remove an association between the two documents and create a log entry
    in the association history table with the given user id.
    """
    association = Association(
        parent_document_id=parent_document_id,
        child_document_id=child_document_id)

    if check_first and not exists_already(association):
        return

    DBSession.query(Association).filter_by(
        parent_document_id=parent_document_id,
        child_document_id=child_document_id).delete()
    DBSession.add(association.get_log(user_id, is_creation=False))


def create_associations(document, associations_for_document, user_id):
    """ Create associations for a document that were provided when creating
    a document.
    """
    main_id = document.document_id
    for doc_key, docs in associations_for_document.items():
        for doc in docs:
            linked_document_id = doc['document_id']
            is_parent = doc['is_parent']

            parent_id = linked_document_id if is_parent else main_id
            child_id = main_id if is_parent else linked_document_id
            add_association(parent_id, child_id, user_id, check_first=False)


def synchronize_associations(document, new_associations, user_id):
    """ Synchronize the associations when updating a document.
    """
    current_associations = _get_current_associations(
        document, new_associations)
    to_add, to_remove = _diff_associations(
        new_associations, current_associations)

    document_id = document.document_id
    _apply_operation(to_add, add_association, document_id, user_id)
    _apply_operation(to_remove, remove_association, document_id, user_id)


def _apply_operation(docs, add_or_remove, document_id, user_id):
    for doc in docs:
        is_parent = doc['is_parent']
        parent_id = doc['document_id'] if is_parent else document_id
        child_id = document_id if is_parent else doc['document_id']
        add_or_remove(parent_id, child_id, user_id, check_first=False)


def _get_current_associations(document, new_associations):
    """ Load the current associations of a document (only those association
    types are loaded that are also given in `new_association`).
    """
    updatable_types = updatable_associations.get(document.type, set())
    types_to_load = updatable_types.intersection(new_associations.keys())
    doc_types_to_load = {association_keys[t] for t in types_to_load}

    if not doc_types_to_load:
        return {}

    current_associations = {t: [] for t in types_to_load}
    query = _get_load_associations_query(document, doc_types_to_load)

    for document_id, doc_type, parent in query:
        is_parent = parent == 1

        association_type = association_keys_for_types[doc_type]
        if doc_type == WAYPOINT_TYPE and document.type == WAYPOINT_TYPE:
            association_type = 'waypoint_parents' if is_parent \
                else 'waypoint_children'

        current_associations[association_type].append({
            'document_id': document_id,
            'is_parent': is_parent
        })

    return current_associations


def _get_load_associations_query(document, doc_types_to_load):
    query_parents = DBSession. \
        query(
            Association.parent_document_id.label('id'),
            Document.type.label('t'),
            literal_column('1').label('p')). \
        join(
            Document,
            and_(
                Association.child_document_id == document.document_id,
                Association.parent_document_id == Document.document_id,
                Document.type.in_(doc_types_to_load))). \
        subquery()
    query_children = DBSession. \
        query(
            Association.child_document_id.label('id'),
            Document.type.label('t'),
            literal_column('0').label('p')). \
        join(
            Document,
            and_(
                Association.child_document_id == Document.document_id,
                Association.parent_document_id == document.document_id,
                Document.type.in_(doc_types_to_load))). \
        subquery()

    return DBSession \
        .query('id', 't', 'p') \
        .select_from(union(query_parents.select(), query_children.select()))


def _diff_associations(new_associations, current_associations):
    """ Given two dicts with associated documents for each association type,
    detect which associations have to be added or removed.
    """
    to_add = _get_associations_to_add(
        new_associations, current_associations)
    to_remove = _get_associations_to_add(
        current_associations, new_associations)
    return to_add, to_remove


def _get_associations_to_add(new_associations, current_associations):
    to_add = []

    for typ, docs in new_associations.items():
        existing_docs = {
            d['document_id'] for d in current_associations.get(typ, [])
        }

        for doc in docs:
            if doc['document_id'] not in existing_docs:
                to_add.append(doc)

    return to_add
