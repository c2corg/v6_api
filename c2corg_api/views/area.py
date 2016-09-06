from c2corg_api.models.area import schema_area, Area, schema_update_area, \
    schema_listing_area, AREA_TYPE
from c2corg_api.models.area_association import update_area
from c2corg_api.models.cache_version import update_cache_version_for_area
from c2corg_api.models.document import UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_common.fields_area import fields_area
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, GetDocumentsConfig
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, validate_lang
from pyramid.httpexceptions import HTTPBadRequest

validate_area_create = make_validator_create(fields_area.get('required'))
validate_area_update = make_validator_update(fields_area.get('required'))


@resource(collection_path='/areas', path='/areas/{id}',
          cors_policy=cors_policy)
class AreaRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(AREA_TYPE, area_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Area, schema_area, include_areas=False)

    @restricted_json_view(
            schema=schema_area, validators=validate_area_create,
            permission='moderator')
    def collection_post(self):
        return self._collection_post(
            schema_area, after_add=insert_associations)

    @restricted_json_view(
            schema=schema_update_area,
            validators=[validate_id, validate_area_update])
    def put(self):
        if not self.request.has_permission('moderator'):
            # the geometry of areas should not be modifiable for non-moderators
            if self.request.validated['document'] and \
                    self.request.validated['document']['geometry']:
                raise HTTPBadRequest('No permission to change the geometry')

        return self._put(Area, schema_area, after_update=update_associations)

area_documents_config = GetDocumentsConfig(
    AREA_TYPE, Area, schema_listing_area, include_areas=False)


@resource(path='/areas/{id}/{lang}/info', cors_policy=cors_policy)
class AreaInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Area)


def insert_associations(area, user_id):
    """Create links between this new area and documents.
    """
    update_area(area, reset=False)


def update_associations(area, update_types, user_id):
    """Update the links between this area and documents when the geometry
    has changed.
    """
    if update_types:
        # update cache key for currently associated docs
        update_cache_version_for_area(area)

    if UpdateType.GEOM in update_types:
        update_area(area, reset=True)
