from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint, WaypointLocale, WAYPOINT_TYPE
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.views import set_best_locale
from c2corg_api.views.validation import updatable_associations, \
    association_keys, association_keys_for_types
from colanderalchemy.schema import SQLAlchemySchemaNode
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    DateTime,
    ForeignKey,
    String
    )
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.orm import relationship, joinedload, load_only

from c2corg_api.models import Base, schema, users_schema, DBSession
from c2corg_api.models.document import Document, DocumentLocale
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
        nullable=False, index=True)
    parent_document = relationship(
        Document, primaryjoin=parent_document_id == Document.document_id)
    parent_document_type = Column(String(1), nullable=False, index=True)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False, index=True)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)
    child_document_type = Column(String(1), nullable=False, index=True)

    __table_args__ = (
        PrimaryKeyConstraint(parent_document_id, child_document_id),
        Base.__table_args__
    )

    @staticmethod
    def create(parent_document, child_document):
        return Association(
            parent_document_id=parent_document.document_id,
            parent_document_type=parent_document.type,
            child_document_id=child_document.document_id,
            child_document_type=child_document.type)

    def get_log(self, user_id, is_creation=True):
        return AssociationLog(
            parent_document_id=self.parent_document_id,
            parent_document_type=self.parent_document_type,
            child_document_id=self.child_document_id,
            child_document_type=self.child_document_type,
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
    parent_document_type = Column(String(1), nullable=False)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)
    child_document_type = Column(String(1), nullable=False)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)

    is_creation = Column(Boolean, default=True, nullable=False)
    written_at = Column(
        DateTime, default=func.now(), nullable=False, index=True)

schema_association = SQLAlchemySchemaNode(
    Association,
    # whitelisted attributes
    includes=['parent_document_id', 'child_document_id'],
    overrides={})


def get_associations(document, lang, editing_view):
    """Load and return associated documents.
    """
    types_to_include = associations_to_include.get(document.type, set())

    if editing_view:
        edit_types = updatable_associations.get(document.type, set())
        types_to_include = types_to_include.intersection(edit_types)

    associations = {}
    if 'waypoints' in types_to_include and \
            'waypoint_children' in types_to_include:
        associations['waypoints'] = get_linked_waypoint_parents(document)
        associations['waypoint_children'] = \
            get_linked_waypoint_children(document)
    elif 'waypoints' in types_to_include:
        waypoint_parents = get_linked_waypoint_parents(document)
        waypoint_children = get_linked_waypoint_children(document)
        associations['waypoints'] = waypoint_parents + waypoint_children
    if 'routes' in types_to_include:
        if not editing_view and document.type == WAYPOINT_TYPE:
            # for waypoints the routes of child waypoints should also be
            # included (done in WaypointRest)
            pass
        else:
            associations['routes'] = get_linked_routes(document)
    if 'users' in types_to_include:
        associations['users'] = get_linked_users(document)
    if 'images' in types_to_include:
        associations['images'] = get_linked_images(document)

    if lang:
        for typ, docs in associations.items():
            if typ != 'users':
                set_best_locale(docs, lang)

    return associations


def _limit_waypoint_fields(query):
    return query. \
        options(load_only(
            Waypoint.waypoint_type, Waypoint.document_id,
            Waypoint.elevation, Waypoint.version, Waypoint.protected)). \
        options(joinedload(Waypoint.locales).load_only(
            WaypointLocale.lang, WaypointLocale.title,
            WaypointLocale.version))


def get_linked_waypoint_parents(document):
    return _limit_waypoint_fields(
        DBSession.query(Waypoint).
        options(joinedload(Waypoint.geometry).load_only(
            DocumentGeometry.geom, DocumentGeometry.version)).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             Association.parent_document_id == Waypoint.document_id).
        filter(Association.child_document_id == document.document_id)). \
        all()


def get_linked_waypoint_children(document):
    return _limit_waypoint_fields(
        DBSession.query(Waypoint).
        options(joinedload(Waypoint.geometry).load_only(
            DocumentGeometry.geom, DocumentGeometry.version)).
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


def get_linked_routes(document):
    condition_as_child = and_(
        Association.child_document_id == Route.document_id,
        Association.parent_document_id == document.document_id)
    condition_as_parent = and_(
        Association.child_document_id == document.document_id,
        Association.parent_document_id == Route.document_id)

    if document.type == WAYPOINT_TYPE:
        condition = condition_as_child
    elif document.type in [OUTING_TYPE, IMAGE_TYPE]:
        condition = condition_as_parent
    else:
        condition = or_(condition_as_child, condition_as_parent)

    return limit_route_fields(
        DBSession.query(Route).
        filter(Route.redirects_to.is_(None)).
        join(Association, condition)). \
        all()


def get_linked_users(document):
    return DBSession.query(User). \
        join(Association, Association.parent_document_id == User.id). \
        filter(Association.child_document_id == document.document_id). \
        options(load_only(User.id, User.username)). \
        all()


def _limit_image_fields(query):
    return query.\
        options(load_only(
            Image.document_id, Image.filename, Image.author, Image.version,
            Image.protected)). \
        options(joinedload(Image.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title,
            DocumentLocale.version)). \
        options(joinedload(Image.geometry).load_only(
            DocumentGeometry.geom, DocumentGeometry.version))


def get_linked_images(document):
    return _limit_image_fields(
        DBSession.query(Image).
        filter(Image.redirects_to.is_(None)).
        join(
            Association,
            and_(
                Association.child_document_id == Image.document_id,
                Association.parent_document_id == document.document_id)
            )). \
        all()


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
        parent_document_id, parent_document_type,
        child_document_id, child_document_type, user_id, check_first=False):
    """Create an association between the two documents and create a log entry
    in the association history table with the given user id.
    """
    association = Association(
        parent_document_id=parent_document_id,
        parent_document_type=parent_document_type,
        child_document_id=child_document_id,
        child_document_type=child_document_type)

    if check_first and exists_already(association):
        return

    DBSession.add(association)
    DBSession.add(association.get_log(user_id, is_creation=True))


def remove_association(
        parent_document_id, parent_document_type,
        child_document_id, child_document_type, user_id, check_first=False):
    """Remove an association between the two documents and create a log entry
    in the association history table with the given user id.
    """
    association = Association(
        parent_document_id=parent_document_id,
        parent_document_type=parent_document_type,
        child_document_id=child_document_id,
        child_document_type=child_document_type)

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
    main_doc_type = document.type
    for doc_key, docs in associations_for_document.items():
        doc_type = association_keys[doc_key]
        for doc in docs:
            linked_document_id = doc['document_id']
            is_parent = doc['is_parent']

            parent_id = linked_document_id if is_parent else main_id
            parent_type = doc_type if is_parent else main_doc_type
            child_id = main_id if is_parent else linked_document_id
            child_type = main_doc_type if is_parent else doc_type
            add_association(
                parent_id, parent_type, child_id, child_type,
                user_id, check_first=False)


def synchronize_associations(document, new_associations, user_id):
    """ Synchronize the associations when updating a document.
    """
    current_associations = _get_current_associations(
        document, new_associations)
    to_add, to_remove = _diff_associations(
        new_associations, current_associations)

    added_associations = _apply_operation(
        to_add, add_association, document, user_id)
    removed_associations = _apply_operation(
        to_remove, remove_association, document, user_id)

    return added_associations, removed_associations


def _apply_operation(docs, add_or_remove, document, user_id):
    associations = []
    main_doc_type = document.type
    for doc in docs:
        is_parent = doc['is_parent']
        parent_id = doc['document_id'] if is_parent else document.document_id
        parent_type = doc['doc_type'] if is_parent else main_doc_type
        child_id = document.document_id if is_parent else doc['document_id']
        child_type = main_doc_type if is_parent else doc['doc_type']

        add_or_remove(
            parent_id, parent_type, child_id, child_type,
            user_id, check_first=False)
        associations.append({
            'parent_id': parent_id,
            'parent_type': parent_type,
            'child_id': child_id,
            'child_type': child_type
        })

    return associations


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
            association_type = 'waypoints' if is_parent \
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
            Association.parent_document_type.label('t'),
            literal_column('1').label('p')). \
        filter(
            and_(
                Association.child_document_id == document.document_id,
                Association.parent_document_type.in_(doc_types_to_load)
            )
        ). \
        subquery()
    query_children = DBSession. \
        query(
            Association.child_document_id.label('id'),
            Association.child_document_type.label('t'),
            literal_column('0').label('p')). \
        filter(
            and_(
                Association.parent_document_id == document.document_id,
                Association.child_document_type.in_(doc_types_to_load)
            )
        ). \
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
        doc_type = association_keys[typ]
        existing_docs = {
            d['document_id'] for d in current_associations.get(typ, [])
        }

        for doc in docs:
            if doc['document_id'] not in existing_docs:
                doc['doc_type'] = doc_type
                to_add.append(doc)

    return to_add

associations_to_include = {
    WAYPOINT_TYPE: {
        'waypoints', 'waypoint_children', 'routes', 'images'},
    ROUTE_TYPE:
        {'waypoints', 'routes', 'images'},
    OUTING_TYPE:
        {'waypoints', 'routes', 'images', 'users'},
    IMAGE_TYPE:
        {'waypoints', 'routes', 'images', 'users', 'outings'}
}
