from sqlalchemy.sql.schema import Column, ForeignKey, Index
from sqlalchemy.sql.sqltypes import Integer, String

from c2corg_api.models import Base, schema


class ImageEmbed(Base):
    """An image shown in the text of a locale by an [img=ID] tag."""

    # Kept up to date when a locale is saved (views.document, the versions
    # written for a creation, an update, a revert or a restore) and removed
    # with the locale (cascade). The image is not a foreign key: an id that
    # does not exist, is not an image or was deleted is a broken embed, found
    # by joining the documents. A merged image still shows (its target), its
    # embeds are not rewritten.

    __tablename__ = 'image_embeds'

    document_locale_id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id', ondelete='CASCADE'),
        primary_key=True,
    )

    image_id = Column(Integer, primary_key=True)

    # the document and lang of the locale, which never change
    document_id = Column(Integer, nullable=False)

    lang = Column(String(2), nullable=False)

    __table_args__ = (
        Index('ix_guidebook_image_embeds_image_id', 'image_id'),
        Index('ix_guidebook_image_embeds_document_id', 'document_id'),
        {'schema': schema},
    )
