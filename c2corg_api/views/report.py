import functools
from c2corg_api.models.report import (
  Report,
  schema_report,
  schema_create_report,
  schema_update_report,
  REPORT_TYPE, ArchiveReport, ArchiveReportLocale, ReportLocale)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_common.fields_report import fields_report
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.views.document_schemas import report_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations, validate_lang, validate_version_id

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
        return self._get(Report, schema_report, clazz_locale=ReportLocale)

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
        return self._put(Report, schema_report)


@resource(path='/reports/{id}/{lang}/{version_id}',
          cors_policy=cors_policy)
class ReportsVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveReport, ArchiveReportLocale, schema_report)


@resource(path='/reports/{id}/{lang}/info', cors_policy=cors_policy)
class ReportsInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Report)
