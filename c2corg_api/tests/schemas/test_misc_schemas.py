import colander

from c2corg_api.models.association import Association, schema_association
from c2corg_api.models.common.attributes import activities, default_langs
from c2corg_api.models.schema_utils import SchemaAssociationDoc
from c2corg_api.schemas.association import AssociationSchema, association_schema
from c2corg_api.tests.schemas.parity import assert_parity
from c2corg_api.views.forum import TopicCreateSchema
from c2corg_api.views.user_preferences import FilterPreferencesSchema


# the Colander schemas these replace, as they were defined in the views
class ColanderFilterPreferences(colander.MappingSchema):
    activities = colander.SchemaNode(
        colander.Sequence(),
        colander.SchemaNode(colander.String(), validator=colander.OneOf(activities)),
        missing=colander.required,
    )
    langs = colander.SchemaNode(
        colander.Sequence(),
        colander.SchemaNode(colander.String(), validator=colander.OneOf(default_langs)),
        missing=colander.required,
    )
    areas = colander.SchemaNode(
        colander.Sequence(), SchemaAssociationDoc(), missing=colander.required
    )
    followed_only = colander.SchemaNode(colander.Boolean(), missing=colander.required)


class ColanderTopicCreate(colander.MappingSchema):
    document_id = colander.SchemaNode(colander.Int())
    lang = colander.SchemaNode(colander.String())


def test_association_parity():
    assert_parity(schema_association, AssociationSchema)
    data = {'parent_document_id': 1, 'child_document_id': 2}
    expected = schema_association.objectify(data)
    actual = association_schema.objectify(data)
    assert isinstance(actual, Association)
    assert (actual.parent_document_id, actual.child_document_id) == (
        expected.parent_document_id,
        expected.child_document_id,
    )


def test_preferences_parity():
    assert_parity(ColanderFilterPreferences(), FilterPreferencesSchema)


def test_topic_parity():
    assert_parity(ColanderTopicCreate(), TopicCreateSchema)
