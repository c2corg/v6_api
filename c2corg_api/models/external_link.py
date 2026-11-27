from sqlalchemy.sql.schema import Column, ForeignKey, Index
from sqlalchemy.sql.sqltypes import Integer, String, Text

from c2corg_api.models import Base, schema


class ExternalLink(Base):
    """A link to another site in the text of a locale, by its URL."""

    # Kept up to date when a locale is saved, with the document links (see
    # views.markdown.update_text_references), and removed with the locale
    # (cascade). The links of merged or deleted documents stay: queries leave
    # them out, as for the document links. The full URLs of the documents of
    # the site are document links, not external links; the other URLs of the
    # site (forum, media...) are external links.

    __tablename__ = 'external_links'

    document_locale_id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id', ondelete='CASCADE'),
        primary_key=True,
    )

    # as the reader gets it (the href of the cooked HTML, unescaped)
    url = Column(Text, primary_key=True)

    # lowercase, without the port nor a final dot: the links of a site
    host = Column(String(255), nullable=False)

    # the document and lang of the locale, which never change
    document_id = Column(Integer, nullable=False)

    lang = Column(String(2), nullable=False)

    __table_args__ = (
        Index('ix_guidebook_external_links_url', 'url'),
        Index('ix_guidebook_external_links_host', 'host'),
        Index('ix_guidebook_external_links_document_id', 'document_id'),
        {'schema': schema},
    )
