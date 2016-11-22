import functools
from c2corg_api.models.report import (
  Report,
  schema_report,
  schema_create_report,
  schema_update_report,
  REPORT_TYPE, ArchiveReport, ArchiveReportLocale, ReportLocale,
  schema_report_without_personal)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_common.fields_report import fields_report
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.views.document_schemas import report_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view, get_creators, \
    set_private_cache_header
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations, validate_lang, validate_version_id

from pyramid.httpexceptions import HTTPForbidden

validate_report_create = make_validator_create(fields_report.get('required'))
validate_report_update = make_validator_update(fields_report.get('required'))
validate_associations_create = functools.partial(
    validate_associations, REPORT_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, REPORT_TYPE, False)


@resource(collection_path='/reports', path='/reports/{id}',
          cors_policy=cors_policy)
class ReportRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(REPORT_TYPE, report_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        set_private_cache_header(self.request)
        if not _has_permission(self.request, self.request.validated['id']):
            # only moderators and the author of a report can access the full
            # report (including personal information)
            return self._get(Report, schema_report_without_personal,
                             clazz_locale=ReportLocale)

        return self._get(Report, schema_report,
                         clazz_locale=ReportLocale,
                         custom_cache_key='private')

    @restricted_json_view(
            schema=schema_create_report,
            validators=[colander_body_validator,
                        validate_report_create,
                        validate_associations_create])
    def collection_post(self):
        return self._collection_post(schema_report)

    @restricted_json_view(
            schema=schema_update_report,
            validators=[colander_body_validator,
                        validate_id,
                        validate_report_update,
                        validate_associations_update])
    def put(self):
        if not _has_permission(self.request, self.request.validated['id']):
            raise HTTPForbidden('No permission to change this report')

        return self._put(Report, schema_report)


def _has_permission(request, report_id):
    """Check if the authenticated user has permission to view non-public
    information of the report or th change the report. That is only
    moderators and users that are currently assigned to the report
    can modify it.
    """
    if request.authorization is None:
        return False

    if request.has_permission('moderator'):
        return True

    user_id = request.authenticated_userid

    creators = get_creators([report_id])
    creator_info = creators.get(report_id)

    return creator_info and creator_info['user_id'] == user_id


@resource(path='/reports/{id}/{lang}/{version_id}',
          cors_policy=cors_policy)
class ReportsVersionRest(DocumentVersionRest):
    @restricted_json_view(validators=[
        validate_id, validate_lang, validate_version_id])
    def get(self):
        set_private_cache_header(self.request)
        if not _has_permission(self.request, self.request.validated['id']):
            raise HTTPForbidden(
                'No permission to view the version of this report')

        return self._get_version(
            ArchiveReport, ArchiveReportLocale, schema_report)


@resource(path='/reports/{id}/{lang}/info', cors_policy=cors_policy)
class ReportsInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Report)
