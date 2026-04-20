from sqlalchemy import ForeignKey, Integer, and_, literal_column, or_, select
from sqlalchemy.orm import (
    Mapped,
    Session,
    joinedload,
    load_only,
    mapped_column,
    relationship,
)
from sqlalchemy.schema import PrimaryKeyConstraint

from c2corg_api.models import Base, DBSession, schema
from c2corg_api.models.cache_version import update_cache_version_for_map
from c2corg_api.models.document import Document, DocumentGeometry, DocumentLocale
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap
from c2corg_api.routers.helpers.document_helpers import set_best_locale


class TopoMapAssociation(Base):
    """Associations between documents and maps.

    Used to cache which documents are within the area of a map. The entries in
    this table are created automatically when a maps is changed/added, when a
    document is added or a document geometry changes.
    """

    __tablename__ = 'map_associations'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), nullable=False
    )
    document = relationship(Document, primaryjoin=document_id == Document.document_id)

    topo_map_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.maps.document_id'), nullable=False
    )
    topo_map = relationship(TopoMap, primaryjoin=topo_map_id == TopoMap.document_id)

    __table_args__ = (
        PrimaryKeyConstraint(document_id, topo_map_id),
        Base.__table_args__,
    )


Document._maps = relationship(
    TopoMap, secondary=TopoMapAssociation.__table__, viewonly=True, cascade='expunge'
)


def update_map(topo_map, reset=False, *, db: Session):
    """Create associations for the given map with all intersecting documents.

    If `reset` is True, all possible existing associations to this map are
    dropped before creating new associations.
    """
    if reset:
        db.execute(
            TopoMapAssociation.__table__.delete().where(
                TopoMapAssociation.topo_map_id == topo_map.document_id
            )
        )

    if topo_map.redirects_to:
        # ignore forwarded maps
        return

    map_geom = select(DocumentGeometry.geom_detail).where(
        DocumentGeometry.document_id == topo_map.document_id
    )
    intersecting_documents = (
        db.query(
            DocumentGeometry.document_id,  # id of a document
            literal_column(str(topo_map.document_id)),
        )
        .join(
            Document,
            and_(
                Document.document_id == DocumentGeometry.document_id,
                Document.type != MAP_TYPE,
            ),
        )
        .filter(Document.redirects_to.is_(None))
        .filter(
            or_(
                DocumentGeometry.geom.ST_Intersects(map_geom.label('t1')),
                DocumentGeometry.geom_detail.ST_Intersects(map_geom.label('t2')),
            )
        )
    )

    db.execute(
        TopoMapAssociation.__table__.insert().from_select(
            [TopoMapAssociation.document_id, TopoMapAssociation.topo_map_id],
            intersecting_documents,
        )
    )

    # update cache key for now associated docs
    update_cache_version_for_map(topo_map, db=db)


def update_maps_for_document(document, reset=False, *, db: Session):
    """Create associations for the given documents with all intersecting maps.

    If `reset` is True, all possible existing associations to this document are
    dropped before creating new associations.
    """
    if reset:
        db.execute(
            TopoMapAssociation.__table__.delete().where(
                TopoMapAssociation.document_id == document.document_id
            )
        )

    if document.redirects_to:
        # ignore forwarded maps
        return

    document_geom = select(DocumentGeometry.geom).where(
        DocumentGeometry.document_id == document.document_id
    )
    document_geom_detail = select(DocumentGeometry.geom_detail).where(
        DocumentGeometry.document_id == document.document_id
    )
    intersecting_maps = (
        db.query(
            DocumentGeometry.document_id,  # id of a map
            literal_column(str(document.document_id)),
        )
        .join(TopoMap, TopoMap.document_id == DocumentGeometry.document_id)
        .filter(TopoMap.redirects_to.is_(None))
        .filter(
            or_(
                DocumentGeometry.geom_detail.ST_Intersects(document_geom.label('t1')),
                DocumentGeometry.geom_detail.ST_Intersects(
                    document_geom_detail.label('t2')
                ),
            )
        )
    )

    db.execute(
        TopoMapAssociation.__table__.insert().from_select(
            [TopoMapAssociation.topo_map_id, TopoMapAssociation.document_id],
            intersecting_maps,
        )
    )


def get_maps(document, lang, db: Session):
    """Load and return areas linked with the given document."""
    maps = (
        db.query(TopoMap)
        .filter(TopoMap.redirects_to.is_(None))
        .join(TopoMapAssociation, TopoMap.document_id == TopoMapAssociation.topo_map_id)
        .options(
            load_only(
                TopoMap.document_id,
                TopoMap.version,
                TopoMap.protected,
                TopoMap.editor,
                TopoMap.scale,
                TopoMap.code,
            )
        )
        .options(
            joinedload(TopoMap.locales).load_only(
                DocumentLocale.lang, DocumentLocale.title, DocumentLocale.version
            )
        )
        .filter(TopoMapAssociation.document_id == document.document_id)
        .all()
    )

    if lang is not None:
        set_best_locale(maps, lang, db=db)

    return maps
