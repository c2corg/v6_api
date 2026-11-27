"""The pairs of images a moderator told are not duplicates."""

from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import CheckConstraint, Column, ForeignKey
from sqlalchemy.sql.sqltypes import DateTime, Integer

from c2corg_api.models import Base, schema, users_schema


class DismissedImageDuplicate(Base):
    """Two images listed as duplicates that are not (see views.image_duplicates)."""

    # One row by pair, the lower id first: a set of images is hidden while all
    # its pairs are dismissed, an image added to it shows it again.
    # The rows go with the images (ON DELETE CASCADE), the soft delete keeps
    # them (views.document_trash).

    __tablename__ = 'dismissed_image_duplicates'
    __table_args__ = (
        CheckConstraint(
            'image1_id < image2_id', name='dismissed_image_duplicates_ordered'
        ),
        {'schema': schema},
    )

    image1_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id', ondelete='CASCADE'),
        primary_key=True,
    )

    image2_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id', ondelete='CASCADE'),
        primary_key=True,
        index=True,
    )

    dismissed_by = Column(
        Integer, ForeignKey(users_schema + '.user.id', ondelete='SET NULL')
    )

    dismissed_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
