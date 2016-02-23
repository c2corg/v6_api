from c2corg_api.models import schema
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_update_schema, geometry_schema_overrides,
    schema_document_locale, schema_attributes)
from c2corg_api.models.enums import user_category, activity_type
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_common.fields_area import fields_area
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )

USERPROFILE_TYPE = 'u'


class _UserProfileMixin(object):
    activities = Column(ArrayOfEnum(activity_type))
    category = Column(user_category)

attributes = ['activities', 'category']


class UserProfile(_UserProfileMixin, Document):
    """
    """
    __tablename__ = 'user_profiles'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': USERPROFILE_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

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
            'children': [schema_document_locale]
        },
        'geometry': geometry_schema_overrides
    })

schema_update_user_profile = get_update_schema(schema_user_profile)
schema_listing_user_profile = restrict_schema(
    schema_user_profile, fields_area.get('listing'))
