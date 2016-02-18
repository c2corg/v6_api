from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale
from c2corg_common.fields_outing import fields_outing
from cornice.resource import resource, view


from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_common.attributes import activities

validate_route_create = make_validator_create(
    fields_outing, 'activities', activities, document_field='outing')
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)


def adapt_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_outing, activities, field_list_type)
    return restrict_schema(schema_outing, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'listing')


@resource(collection_path='/outings', path='/outings/{id}',
          cors_policy=cors_policy)
class OutingRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            Outing, schema_outing, listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Outing, schema_outing, schema_adaptor)

    @restricted_json_view(schema=schema_create_outing,
                          validators=validate_route_create)
    def collection_post(self):
        # TODO set up associations in after_add
        return self._collection_post(schema_outing, document_field='outing')

    @restricted_json_view(schema=schema_update_outing,
                          validators=[validate_id, validate_outing_update])
    def put(self):
        return self._put(Outing, schema_outing)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, ArchiveOutingLocale, schema_outing, schema_adaptor)
