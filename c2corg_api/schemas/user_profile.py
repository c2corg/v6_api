"""Schemas of the user profiles."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.common.fields_user_profile import fields_user_profile
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.schemas.base import ModelSchema, Schema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Int, Map, OneOf, Seq, Str

UserProfileGeometrySchema = geometry_schema(['POINT'])


class UserProfileLocaleSchema(Schema):
    # no title: the title of a profile is the name of its user
    version: Int = None
    lang: Str(2)
    description: Str() = None
    summary: Str() = None


class UserProfileSchema(DocumentSchema):
    locales: Seq(UserProfileLocaleSchema) = []
    geometry: Map(UserProfileGeometrySchema) = None
    activities: Seq(OneOf(a.activities)) = None
    categories: Seq(OneOf(a.user_categories)) = None


UserProfileUpdateSchema = update_schema(
    create_schema(UserProfileSchema, AssociationsSchema)
)

user_profile_schema = ModelSchema(
    UserProfile,
    UserProfileSchema,
    document_children(
        locale_schema=UserProfileLocaleSchema, geometry=UserProfileGeometrySchema
    ),
)
# the same, with the locale titles that the update view sets to ''
internal_user_profile_schema = ModelSchema(
    UserProfile,
    UserProfileSchema,
    document_children(geometry=UserProfileGeometrySchema),
)
user_profile_listing_schema = user_profile_schema.restrict(
    fields_user_profile.get('listing')
)
