from datetime import timedelta

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import DateTime, Integer, String

from c2corg_api.models import Base, schema, users_schema

# How long a deleted document can be restored. Under the 30 days the image
# bucket keeps the versions of the deleted files (c2corg-active), so that the
# files of a deleted image can be restored as long as the document can.
RETENTION = timedelta(days=29)


class DeletedDocument(Base):
    """A deleted document or locale, kept for a while to be restored."""

    # The rows the deletion removed are kept in `snapshot` (see
    # views.document_trash): the tables of the documents stay as they were,
    # no query has to filter deleted documents out.

    __tablename__ = 'deleted_documents'

    id = Column(Integer, primary_key=True)

    document_id = Column(Integer, nullable=False, index=True)

    document_type = Column(String(1), nullable=False)

    # the deleted locale, null when the whole document was deleted
    lang = Column(String(2), ForeignKey(schema + '.langs.lang'))

    # the title of the document when deleted, for the list of the moderators
    title = Column(String(150))

    deleted_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    deleted_by = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    restored_at = Column(DateTime(timezone=True))

    restored_by = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    # {table name: [rows as JSON]} plus the changes to undo besides the
    # removed rows (see views.document_trash)
    snapshot = Column(JSONB, nullable=False)

    __table_args__ = {'schema': schema}
