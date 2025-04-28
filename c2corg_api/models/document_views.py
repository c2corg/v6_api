from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Boolean,
    )
from sqlalchemy.orm import relationship

from c2corg_api.models import schema, Base
from c2corg_api.models.document import Document

class DocumentViews(Base):
    """
    Mapping between document and the nombre of it's views
    """
    __tablename__ = 'document_views'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),primary_key=True,
        nullable=False, index=True)

    view_count = Column(Integer, default = 0)
    enable_view_count = Column( Boolean, default=True)

    document = relationship(
        Document, primaryjoin=document_id == Document.document_id)