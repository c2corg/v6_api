from typing import List, Optional

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_user_profile import fields_user_profile
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    geometry_attributes,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.enums import activity_type, user_category
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

USERPROFILE_TYPE = document_types.USERPROFILE_TYPE


class _UserProfileMixin:
    activities: Mapped[Optional[List[str]]] = mapped_column(ArrayOfEnum(activity_type))
    categories: Mapped[Optional[List[str]]] = mapped_column(ArrayOfEnum(user_category))


attributes = ['activities', 'categories']


class UserProfile(_UserProfileMixin, Document):
    """The user profile for each user
    User profile documents are created automatically when creating a new user.
    """

    __tablename__ = 'user_profiles'

    document_id: Mapped[int] = mapped_column(
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
        super(UserProfile, self)._to_archive(user_profile)
        copy_attributes(self, user_profile, attributes)

        return user_profile

    def update(self, other):
        super(UserProfile, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveUserProfile(_UserProfileMixin, ArchiveDocument):
    """ """

    __tablename__ = 'user_profiles_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


# user profiles use a special locale which ignores the 'title'
# attribute (user profiles do not have a title).
_user_profile_locale_fields = ['version', 'lang', 'description', 'summary']

schema_user_profile = build_field_spec(
    UserProfile,
    includes=schema_attributes + attributes,
    locale_fields=_user_profile_locale_fields,
    geometry_fields=geometry_attributes,
)

schema_internal_user_profile = build_field_spec(
    UserProfile,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_user_profile = schema_user_profile.restrict(
    fields_user_profile.get('listing')
)
