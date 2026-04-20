from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from c2corg_api.models import Base, schema
from c2corg_api.models.document import DocumentLocale


class DocumentTopic(Base):
    """
    Mapping between document locales and the corresponding Discourse topics
    for the comments.
    """

    __tablename__ = 'documents_topics'

    document_locale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    document_locale = relationship(
        DocumentLocale, backref=backref('document_topic', uselist=False, lazy='select')
    )
