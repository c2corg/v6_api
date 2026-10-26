"""Schema of an association between two documents."""

from c2corg_api.models.association import Association
from c2corg_api.schemas.base import ModelSchema, Schema
from c2corg_api.schemas.types import Int


class AssociationSchema(Schema):
    parent_document_id: Int
    child_document_id: Int


association_schema = ModelSchema(Association, AssociationSchema)
