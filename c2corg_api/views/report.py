import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import ArchiveDocument
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.report import (
  Report,
  schema_report,
  schema_create_report,
  schema_update_report,
  REPORT_TYPE, ArchiveReport, ArchiveReportLocale, ReportLocale,
  schema_report_without_personal)
from c2corg_api.models.user import User
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
from sqlalchemy.sql.expression import and_, over
from sqlalchemy.sql.functions import func

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
        if self.request.authorization is None:
            return self._get(Report, schema_report_without_personal,
                             clazz_locale=ReportLocale)

        if not self.request.has_permission('moderator'):

            if not self._has_permission(self.request.authenticated_userid,
                                        self.request.validated['id']):
                return self._get(Report, schema_report_without_personal,
                                 clazz_locale=ReportLocale)

            return self._get(Report, schema_report,
                             clazz_locale=ReportLocale,
                             custom_cache_key='moderator')

        return self._get(Report, schema_report,
                         clazz_locale=ReportLocale,
                         custom_cache_key='moderator')

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
        if self.request.authorization is None:
            raise HTTPForbidden('No permission to change this report')

        if not self.request.has_permission('moderator'):
            # moderators can change every outing

            if not self._has_permission(
                    self.request.authenticated_userid,
                    self.request.validated['id']):
                # but a normal user can only change a report that he created
                # are associated to
                raise HTTPForbidden('No permission to change this report')

            return self._put(Report, schema_report)

        return self._put(Report, schema_report)

    def _has_permission(self, user_id, report_id):
        """Check if the user with the given id has permission to change the
        report. That is only users that are currently assigned to the report
        can modify it.
        """

        if not report_id:
            return False

        t = DBSession.query(
            ArchiveDocument.document_id.label('document_id'),
            User.id.label('user_id'),
            User.name.label('name'),
            over(
                func.rank(), partition_by=ArchiveDocument.document_id,
                order_by=HistoryMetaData.id).label('rank')). \
            select_from(ArchiveDocument). \
            join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1)). \
            join(HistoryMetaData,
                 DocumentVersion.history_metadata_id == HistoryMetaData.id). \
            join(User,
                 HistoryMetaData.user_id == User.id). \
            filter(ArchiveDocument.document_id == report_id). \
            subquery('t')

        query = DBSession.query(
            t.c.document_id, t.c.user_id, t.c.name). \
            filter(t.c.rank == 1)

        author_for_documents = {
            document_id: {
                'username': username,
                'user_id': user_id
            } for document_id, user_id, username in query
        }

        if len(author_for_documents) > 0:
            for document in author_for_documents:
                if document == report_id:
                    return True
        else:
            return False


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
