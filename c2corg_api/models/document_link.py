from sqlalchemy.sql.schema import Column, ForeignKey, Index
from sqlalchemy.sql.sqltypes import Boolean, Integer, String

from c2corg_api.models import Base, schema
from c2corg_api.models.common.document_types import (
    AREA_TYPE,
    ARTICLE_TYPE,
    BOOK_TYPE,
    IMAGE_TYPE,
    MAP_TYPE,
    OUTING_TYPE,
    ROUTE_TYPE,
    USERPROFILE_TYPE,
    WAYPOINT_TYPE,
    XREPORT_TYPE,
)

# the type of the document of a link, by the type written in it: the pages of
# the site (/routes/123...)
LINK_TYPES = {
    'areas': AREA_TYPE,
    'articles': ARTICLE_TYPE,
    'books': BOOK_TYPE,
    'images': IMAGE_TYPE,
    'maps': MAP_TYPE,
    'outings': OUTING_TYPE,
    'profiles': USERPROFILE_TYPE,
    'routes': ROUTE_TYPE,
    'waypoints': WAYPOINT_TYPE,
    'xreports': XREPORT_TYPE,
}

# the type written in a link, by the type of its document
LINK_TYPE_NAMES = {letter: name for name, letter in LINK_TYPES.items()}


class DocumentLink(Base):
    """A document linked in the text of a locale: [[type/id|label]] or a URL."""

    # Kept up to date when a locale is saved, with the image embeds (see
    # views.markdown.update_text_references), and removed with the locale
    # (cascade). The target is not a foreign key: an id that does not exist,
    # was deleted or is of another type than the link says is a broken link,
    # found by joining the documents. A merged target redirects: not broken.

    __tablename__ = 'document_links'

    document_locale_id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id', ondelete='CASCADE'),
        primary_key=True,
    )

    target_id = Column(Integer, primary_key=True)

    # the type as written in the link, e.g. "routes", or "summits" (v5)
    target_type = Column(String(20), primary_key=True)

    # written as a full URL of the site, not as [[type/id|label]]
    is_url = Column(Boolean, nullable=False)

    # the document and lang of the locale, which never change
    document_id = Column(Integer, nullable=False)

    lang = Column(String(2), nullable=False)

    __table_args__ = (
        Index('ix_guidebook_document_links_target_id', 'target_id'),
        Index('ix_guidebook_document_links_document_id', 'document_id'),
        {'schema': schema},
    )
