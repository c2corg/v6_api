from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
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
from sqlalchemy.orm import relationship

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
        child_document_id, child_document_type, user_id, check_first=False,
        check_association=None):
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

    if check_association:
        check_association(association)

    DBSession.add(association)
    DBSession.add(association.get_log(user_id, is_creation=True))


def remove_association(
        parent_document_id, parent_document_type,
        child_document_id, child_document_type, user_id, check_first=False,
        check_association=None):
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

    if check_association:
        check_association(association)

    DBSession.query(Association).filter_by(
        parent_document_id=parent_document_id,
        child_document_id=child_document_id).delete()
    DBSession.add(association.get_log(user_id, is_creation=False))


def create_associations(
        document, associations_for_document, user_id, check_association=None):
    """ Create associations for a document that were provided when creating
    a document.
    """
    added_associations = []
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
                user_id, check_first=False,
                check_association=check_association)
            added_associations.append({
                'parent_id': parent_id,
                'parent_type': parent_type,
                'child_id': child_id,
                'child_type': child_type
            })
    return added_associations


def synchronize_associations(
        document, new_associations, user_id, check_association=None):
    """ Synchronize the associations when updating a document.
    """
    current_associations = _get_current_associations(
        document, new_associations)
    to_add, to_remove = _diff_associations(
        new_associations, current_associations)

    added_associations = _apply_operation(
        to_add, add_association, document, user_id, check_association)
    removed_associations = _apply_operation(
        to_remove, remove_association, document, user_id, check_association)

    return added_associations, removed_associations


def _apply_operation(
        docs, add_or_remove, document, user_id, check_association):
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
            user_id, check_first=False, check_association=check_association)
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

association_keys = {
    'routes': ROUTE_TYPE,
    'waypoints': WAYPOINT_TYPE,
    'waypoint_children': WAYPOINT_TYPE,
    'users': USERPROFILE_TYPE,
    'images': IMAGE_TYPE,
    'articles': ARTICLE_TYPE,
    'areas': AREA_TYPE,
    'books': BOOK_TYPE,
    'outings': OUTING_TYPE,
    'xreports': XREPORT_TYPE
}

association_keys_for_types = {
    ROUTE_TYPE: 'routes',
    WAYPOINT_TYPE: 'waypoints',
    USERPROFILE_TYPE: 'users',
    ARTICLE_TYPE: 'articles',
    BOOK_TYPE: 'books',
    IMAGE_TYPE: 'images',
    AREA_TYPE: 'areas',
    OUTING_TYPE: 'outings',
    XREPORT_TYPE: 'xreports'
}

# associations that can be updated/created when updating/creating a document
# e.g. when creating a route, route and waypoint associations can be created
updatable_associations = {
    ROUTE_TYPE: {'articles', 'routes', 'waypoints', 'books', 'xreports'},
    WAYPOINT_TYPE: {'articles', 'waypoints', 'waypoint_children', 'xreports'},
    OUTING_TYPE: {'articles', 'routes', 'users', 'xreports'},
    IMAGE_TYPE: {'routes', 'waypoints', 'images', 'users', 'articles',
                 'areas', 'outings', 'books', 'xreports'},
    ARTICLE_TYPE: {'articles', 'images', 'users', 'routes', 'waypoints',
                   'outings', 'books', 'xreports'},
    AREA_TYPE: {'images'},
    BOOK_TYPE: {'routes', 'articles', 'images', 'waypoints'},
    XREPORT_TYPE: {'routes', 'outings', 'articles', 'images'}
}
