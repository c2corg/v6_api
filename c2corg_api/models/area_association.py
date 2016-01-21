from c2corg_api.models import Base, schema, DBSession
from c2corg_api.models.area import Area, AREA_TYPE
from c2corg_api.models.document import Document, DocumentGeometry
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from sqlalchemy.orm import relationship
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import and_


class AreaAssociation(Base):
    """Associations between documents and areas.

    Used to cache which documents are within area. The entries in this table
    are created automatically when an area is changed/added, when a document
    is added or a document geometry changes.
    """
    __tablename__ = 'area_associations'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id)

    area_id = Column(
        Integer, ForeignKey(schema + '.areas.document_id'),
        nullable=False)
    area = relationship(
        Area, primaryjoin=area_id == Area.document_id)

    __table_args__ = (
        PrimaryKeyConstraint(document_id, area_id),
        Base.__table_args__
    )


def update_area(area, reset=False):
    """Create associations for the given area with all intersecting documents.

    If `reset` is True, all possible existing associations to this area are
    dropped before creating new associations.
    """
    if reset:
        DBSession.execute(
            AreaAssociation.__table__.delete().where(
                AreaAssociation.area_id == area.document_id)
        )

    intersecting_documents = DBSession. \
        query(
            DocumentGeometry.document_id,  # id of a document
            literal_column(str(area.document_id))). \
        join(
            Document,
            and_(
                Document.document_id == DocumentGeometry.document_id,
                Document.type != AREA_TYPE)). \
        filter(
            DocumentGeometry.geom.intersects(
                DBSession.query(DocumentGeometry.geom).filter(
                    DocumentGeometry.document_id == area.document_id)
            ))

    DBSession.execute(
        AreaAssociation.__table__.insert().from_select(
            [AreaAssociation.document_id, AreaAssociation.area_id],
            intersecting_documents))


def update_document(document, reset=False):
    """Create associations for the given documents with all intersecting areas.

    If `reset` is True, all possible existing associations to this document are
    dropped before creating new associations.
    """
    if reset:
        DBSession.execute(
            AreaAssociation.__table__.delete().where(
                AreaAssociation.document_id == document.document_id)
        )

    intersecting_areas = DBSession. \
        query(
            DocumentGeometry.document_id,  # id of an area
            literal_column(str(document.document_id))). \
        join(
            # join on the table instead on `Area` to avoid that SQLA adds
            # a join on "guidebook.documents"
            Area.__table__,
            Area.document_id == DocumentGeometry.document_id). \
        filter(
            DocumentGeometry.geom.intersects(
                DBSession.query(DocumentGeometry.geom).filter(
                    DocumentGeometry.document_id == document.document_id)
            ))

    DBSession.execute(
        AreaAssociation.__table__.insert().from_select(
            [AreaAssociation.area_id, AreaAssociation.document_id],
            intersecting_areas))
