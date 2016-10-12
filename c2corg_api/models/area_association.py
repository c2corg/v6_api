from c2corg_api.models import Base, schema, DBSession
from c2corg_api.models.area import Area, AREA_TYPE
from c2corg_api.models.cache_version import update_cache_version_for_area
from c2corg_api.models.document import Document, DocumentGeometry, \
    DocumentLocale
from c2corg_api.views import set_best_locale
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from sqlalchemy.orm import relationship, load_only, joinedload
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import and_, or_, select


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
        Document, primaryjoin=document_id == Document.document_id
    )

    area_id = Column(
        Integer, ForeignKey(schema + '.areas.document_id'),
        nullable=False)
    area = relationship(
        Area, primaryjoin=area_id == Area.document_id)

    __table_args__ = (
        PrimaryKeyConstraint(document_id, area_id),
        Base.__table_args__
    )


Document._areas = relationship(
    Area,
    secondary=AreaAssociation.__table__,
    viewonly=True, cascade='expunge'
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

    if area.redirects_to:
        # ignore forwarded areas
        return

    area_geom = select([DocumentGeometry.geom_detail]). \
        where(DocumentGeometry.document_id == area.document_id)
    intersecting_documents = DBSession. \
        query(
            DocumentGeometry.document_id,  # id of a document
            literal_column(str(area.document_id))). \
        join(
            Document,
            and_(
                Document.document_id == DocumentGeometry.document_id,
                Document.type != AREA_TYPE)). \
        filter(Document.redirects_to.is_(None)). \
        filter(
            or_(
                DocumentGeometry.geom.ST_Intersects(
                    area_geom.label('t1')),
                DocumentGeometry.geom_detail.ST_Intersects(
                    area_geom.label('t2'))
            ))

    DBSession.execute(
        AreaAssociation.__table__.insert().from_select(
            [AreaAssociation.document_id, AreaAssociation.area_id],
            intersecting_documents))

    # update cache key for now associated docs
    update_cache_version_for_area(area)


def update_areas_for_document(document, reset=False):
    """Create associations for the given documents with all intersecting areas.

    If `reset` is True, all possible existing associations to this document are
    dropped before creating new associations.
    """
    if reset:
        DBSession.execute(
            AreaAssociation.__table__.delete().where(
                AreaAssociation.document_id == document.document_id)
        )

    if document.redirects_to:
        # ignore forwarded areas
        return

    document_geom = select([DocumentGeometry.geom]). \
        where(DocumentGeometry.document_id == document.document_id)
    document_geom_detail = select([DocumentGeometry.geom_detail]). \
        where(DocumentGeometry.document_id == document.document_id)
    intersecting_areas = DBSession. \
        query(
            DocumentGeometry.document_id,  # id of an area
            literal_column(str(document.document_id))). \
        join(
            Area,
            Area.document_id == DocumentGeometry.document_id). \
        filter(Area.redirects_to.is_(None)). \
        filter(
            or_(
                DocumentGeometry.geom_detail.ST_Intersects(
                    document_geom.label('t1')),
                DocumentGeometry.geom_detail.ST_Intersects(
                    document_geom_detail.label('t2'))
            ))

    DBSession.execute(
        AreaAssociation.__table__.insert().from_select(
            [AreaAssociation.area_id, AreaAssociation.document_id],
            intersecting_areas))


def get_areas(document, lang):
    """Load and return areas linked with the given document.
    """
    areas = DBSession. \
        query(Area). \
        filter(Area.redirects_to.is_(None)). \
        join(
            AreaAssociation,
            Area.document_id == AreaAssociation.area_id). \
        options(load_only(
            Area.document_id, Area.area_type, Area.version, Area.protected,
            Area.type)). \
        options(joinedload(Area.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title,
            DocumentLocale.version)). \
        filter(
            AreaAssociation.document_id == document.document_id
        ). \
        all()

    if lang is not None:
        set_best_locale(areas, lang)

    return areas
