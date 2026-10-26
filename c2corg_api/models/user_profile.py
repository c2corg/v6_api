from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.ext.associationproxy import association_proxy

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
)
from c2corg_api.models.enums import activity_type, user_category
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

USERPROFILE_TYPE = document_types.USERPROFILE_TYPE


class _UserProfileMixin:
    activities = Column(ArrayOfEnum(activity_type))
    categories = Column(ArrayOfEnum(user_category))


attributes = ['activities', 'categories']


class UserProfile(_UserProfileMixin, Document):
    """The profile of a user.

    The user profile for each user
    User profile documents are created automatically when creating a new user.
    """

    __tablename__ = 'user_profiles'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    name = association_proxy('user', 'name')
    forum_username = association_proxy('user', 'forum_username')

    def to_archive(self):
        user_profile = ArchiveUserProfile()
        super()._to_archive(user_profile)
        copy_attributes(self, user_profile, attributes)

        return user_profile

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveUserProfile(_UserProfileMixin, ArchiveDocument):
    """Archived version of an user profile."""

    __tablename__ = 'user_profiles_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__
