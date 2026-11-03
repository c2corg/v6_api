from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, DBSession, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
)
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

IMAGE_TYPE = document_types.IMAGE_TYPE


class _ImageMixin:
    activities = Column(ArrayOfEnum(enums.activity_type))

    categories = Column(ArrayOfEnum(enums.image_category))

    image_type = Column(enums.image_type)

    author = Column(String(100))

    elevation = Column(SmallInteger)

    height = Column(SmallInteger)

    width = Column(SmallInteger)

    file_size = Column(Integer)

    @declared_attr
    def filename(self):
        return Column(String(30), nullable=False, unique=(self.__name__ == 'Image'))

    date_time = Column(DateTime(timezone=True))

    camera_name = Column(String(100))

    exposure_time = Column(Float)

    focal_length = Column(Float)

    fnumber = Column(Float)

    iso_speed = Column(SmallInteger)


attributes = [
    'activities',
    'categories',
    'image_type',
    'author',
    'elevation',
    'height',
    'width',
    'file_size',
    'filename',
    'camera_name',
    'exposure_time',
    'focal_length',
    'fnumber',
    'iso_speed',
    'date_time',
]


class Image(_ImageMixin, Document):
    """Current version of an image."""

    __tablename__ = 'images'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        image = ArchiveImage()
        super()._to_archive(image)
        copy_attributes(self, image, attributes)

        return image

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveImage(_ImageMixin, ArchiveDocument):
    """Archived version of an image."""

    __tablename__ = 'images_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


def is_personal(image_id):
    image_type = (
        DBSession.query(Image.image_type)
        .select_from(Image.__table__)
        .filter(Image.document_id == image_id)
        .scalar()
    )
    return image_type == 'personal'


def get_image_filenames(image_ids):
    """Map image ids to the filename of the image they show, in one query."""
    return {
        document_id: filename
        for document_id, (filename, _width, _height) in get_shown_images(
            image_ids
        ).items()
    }


def get_shown_images(image_ids):
    """Map image ids to the (filename, width, height) of the image shown."""
    # A merged image redirects to its target and its own files are deleted,
    # so use the target. Merging an already redirected document is refused,
    # there is at most one level of redirection. Unknown ids are left out.
    # width and height are the original's, None when unknown.
    documents = Document.__table__
    images = Image.__table__
    rows = (
        DBSession.query(
            documents.c.document_id,
            images.c.filename,
            images.c.width,
            images.c.height,
        )
        .select_from(documents)
        .join(
            images,
            images.c.document_id
            == func.coalesce(documents.c.redirects_to, documents.c.document_id),
        )
        .filter(documents.c.document_id.in_(image_ids))
        .filter(documents.c.type == IMAGE_TYPE)
        .all()
    )
    return {
        document_id: (filename, width, height)
        for document_id, filename, width, height in rows
    }
