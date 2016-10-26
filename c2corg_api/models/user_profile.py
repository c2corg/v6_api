from c2corg_api.models import schema, Base
from c2corg_api.models.document import (
    ArchiveDocument, Document, geometry_schema_overrides,
    schema_document_locale, schema_attributes, DocumentLocale)
from c2corg_api.models.enums import user_category, activity_type
from c2corg_api.models.schema_utils import restrict_schema, get_update_schema
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_common.fields_user_profile import fields_user_profile
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from c2corg_common import document_types
from sqlalchemy.ext.associationproxy import association_proxy

USERPROFILE_TYPE = document_types.USERPROFILE_TYPE


class _UserProfileMixin(object):
    activities = Column(ArrayOfEnum(activity_type))
    categories = Column(ArrayOfEnum(user_category))

attributes = ['activities', 'categories']


class UserProfile(_UserProfileMixin, Document):
    """The user profile for each user
    User profile documents are created automatically when creating a new user.
    """
    __tablename__ = 'user_profiles'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': Document.document_id == document_id
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
    """
    """
    __tablename__ = 'user_profiles_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


# user profiles use a special schema for the locales which ignores the 'title'
# attribute (user profiles do not have a title).
schema_user_profile_locale = SQLAlchemySchemaNode(
    DocumentLocale,
    # whitelisted attributes (without 'title')
    includes=['version', 'lang', 'description', 'summary'],
    overrides={
        'version': {
            'missing': None
        }
    })


schema_user_profile = SQLAlchemySchemaNode(
    UserProfile,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_user_profile_locale]
        },
        'geometry': geometry_schema_overrides
    })


schema_internal_user_profile = SQLAlchemySchemaNode(
    UserProfile,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_document_locale]
        },
        'geometry': geometry_schema_overrides
    })

schema_update_user_profile = get_update_schema(schema_user_profile)
schema_listing_user_profile = restrict_schema(
    schema_user_profile, fields_user_profile.get('listing'))
