from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import DateTime, Integer, String

from c2corg_api.models import Base, schema, users_schema


class MergedDocument(Base):
    """A merge of two documents, kept for a while to be undone."""

    # What the merge moved from the source to the target, and the rows it
    # removed, are kept in `snapshot` (see views.document_unmerge). Kept as
    # long as a deleted document (models.deleted_document.RETENTION): the
    # files of a merged image can be restored as long.

    __tablename__ = 'merged_documents'

    id = Column(Integer, primary_key=True)

    source_document_id = Column(Integer, nullable=False, index=True)

    target_document_id = Column(Integer, nullable=False, index=True)

    document_type = Column(String(1), nullable=False)

    # the title of the source when merged, for the list of the moderators
    title = Column(String(150))

    # the time of the merge transaction: a change of an association or a
    # favourite after it is not undone
    merged_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # who wrote the source document, the author of its first version: to
    # filter the list of the moderators (as DeletedDocument.author_id)
    author_id = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    merged_by = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    unmerged_at = Column(DateTime(timezone=True))

    unmerged_by = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    snapshot = Column(JSONB, nullable=False)

    __table_args__ = {'schema': schema}
