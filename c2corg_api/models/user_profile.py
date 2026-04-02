from c2corg_api.models import schema, Base
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_geometry_schema_overrides,
    schema_document_locale, schema_attributes, DocumentLocale)
from c2corg_api.models.enums import user_category, activity_type
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_api.models.common.fields_user_profile import fields_user_profile
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from c2corg_api.models.common import document_types
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
        'geometry': get_geometry_schema_overrides(['POINT'])
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
        'geometry': get_geometry_schema_overrides(['POINT'])
    })

schema_listing_user_profile = restrict_schema(
    schema_user_profile, fields_user_profile.get('listing'))


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    DocumentGeometrySchema,
    AssociationsSchema,
    LangType,
    _DuplicateLocalesMixin,
)
from c2corg_api.models.document import (  # noqa: E402
    DocumentLocale, schema_attributes,
)
from pydantic import BaseModel  # noqa: E402, F401
from typing import List, Optional  # noqa: E402

# -- locale schema (no title, mirrors schema_user_profile_locale) ---

_UserProfileLocaleBase = schema_from_sa_model(
    DocumentLocale,
    name='_UserProfileLocaleBase',
    includes=['version', 'lang', 'description', 'summary'],
    overrides={
        'version': {'default': None},
        'lang': {'type': LangType},
    },
)


class UserProfileLocaleSchema(_UserProfileLocaleBase):
    """Locale for user-profile updates (title accepted but ignored)."""
    title: Optional[str] = None
    model_config = {"extra": "ignore"}


# -- document schema (inner "document" key of the PUT body) ---------

_UserProfileDocBase = schema_from_sa_model(
    UserProfile,
    name='_UserProfileDocBase',
    includes=[
        a for a in schema_attributes + attributes
        if a not in ('locales', 'geometry')
    ],
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
    },
)


class UserProfileDocumentSchema(
    _DuplicateLocalesMixin, _UserProfileDocBase,
):
    """Full user-profile document for create/update requests."""
    locales: Optional[List[UserProfileLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


# -- top-level PUT envelope -----------------------------------------

UpdateUserProfileSchema = pydantic_update_schema(
    UserProfileDocumentSchema,
    name='UpdateUserProfileSchema',
)
