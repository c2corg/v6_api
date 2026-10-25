import colander

from c2corg_api.models.common.attributes import default_langs
from c2corg_api.tests.schemas.parity import assert_parity
from c2corg_api.views.document_merge import MergeSchema
from c2corg_api.views.document_protect import ProtectSchema
from c2corg_api.views.document_revert import RevertSchema
from c2corg_api.views.document_tag import DocumentTagSchema
from c2corg_api.views.document_version_mask import MaskSchema
from c2corg_api.views.user_block import BlockSchema
from c2corg_api.views.user_follow import FollowSchema


def _integer():
    return colander.SchemaNode(colander.Integer(), missing=colander.required)


def _lang():
    return colander.SchemaNode(
        colander.String(),
        missing=colander.required,
        validator=colander.OneOf(default_langs),
    )


# the Colander schemas these replace, as they were defined in the views
class ColanderDocumentId(colander.MappingSchema):
    document_id = _integer()


class ColanderUserId(colander.MappingSchema):
    user_id = _integer()


class ColanderMerge(colander.MappingSchema):
    source_document_id = _integer()
    target_document_id = _integer()


class ColanderVersion(colander.MappingSchema):
    document_id = _integer()
    lang = _lang()
    version_id = _integer()


def test_action_schemas_parity():
    for colander_schema, schema in (
        (ColanderDocumentId(), ProtectSchema),
        (ColanderDocumentId(), DocumentTagSchema),
        (ColanderUserId(), FollowSchema),
        (ColanderUserId(), BlockSchema),
        (ColanderMerge(), MergeSchema),
        (ColanderVersion(), RevertSchema),
        (ColanderVersion(), MaskSchema),
    ):
        assert_parity(colander_schema, schema)
