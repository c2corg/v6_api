from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    )
from sqlalchemy.orm import relationship, backref

from c2corg_api.models import schema, Base
from c2corg_api.models.document import DocumentLocale


class DocumentTopic(Base):
    """
    Mapping between document locales and the corresponding Discourse topics
    for the comments.
    """
    __tablename__ = 'documents_topics'

    document_locale_id = Column(Integer,
                                ForeignKey(schema + '.documents_locales.id'),
                                primary_key=True)
    topic_id = Column(Integer, nullable=False, unique=True)

    document_locale = relationship(
            DocumentLocale,
            backref=backref("document_topic", uselist=False, lazy='joined'))
