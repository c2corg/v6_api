import logging

from c2corg_api import DBSession
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.views import cors_policy, restricted_json_view
from colander import (
    MappingSchema, SchemaNode, Integer, String, required, OneOf)
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy.sql.expression import exists, and_

log = logging.getLogger(__name__)


class MaskSchema(MappingSchema):
    document_id = SchemaNode(Integer(), missing=required)
    lang = SchemaNode(String(), missing=required,
                      validator=OneOf(default_langs))
    version_id = SchemaNode(Integer(), missing=required)


def validate_version(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']
    version_id = request.validated['version_id']

    # check the version to mask/unmask actually exists
    version_exists = DBSession.query(
        exists().where(
            and_(DocumentVersion.id == version_id,
                 DocumentVersion.document_id == document_id,
                 DocumentVersion.lang == lang))
    ).scalar()
    if not version_exists:
        raise HTTPBadRequest('Unknown version {}/{}/{}'.format(
            document_id, lang, version_id))

    # check the version to mask/unmask is not the latest one
    latest_version_id, = DBSession.query(DocumentVersion.id). \
        filter(and_(
            DocumentVersion.document_id == document_id,
            DocumentVersion.lang == lang)). \
        order_by(DocumentVersion.id.desc()).first()
    if version_id == latest_version_id:
        raise HTTPBadRequest(
            'Version {}/{}/{} is the latest one'.format(
                document_id, lang, version_id))


def _get_version(request):
    document_id = request.validated['document_id']
    lang = request.validated['lang']
    version_id = request.validated['version_id']

    version = DBSession.query(DocumentVersion).get(version_id)

    if not version:
        raise HTTPBadRequest('Unknown version_id {}'.format(version_id))

    if version.document_id != document_id or version.lang != lang:
        raise HTTPBadRequest('Unknown version {}/{}/{}'.format(
            document_id, lang, version_id))

    return version


@resource(path='/versions/mask', cors_policy=cors_policy)
class VersionMaskRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=MaskSchema(),
        validators=[colander_body_validator, validate_version])
    def post(self):
        """ Mask the given document version.

        Request:
            `POST` `/versions/mask`

        Request body:
            {
                'document_id': @document_id@,
                'lang': @lang@,
                'version_id': @version_id@
            }

        """
        version = _get_version(self.request)
        version.masked = True

        update_cache_version_direct(self.request.validated['document_id'])

        return {}


@resource(path='/versions/unmask', cors_policy=cors_policy)
class VersionUnmaskRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=MaskSchema(),
        validators=[colander_body_validator, validate_version])
    def post(self):
        """ Unmask the given version.

        Request:
            `POST` `/versions/unmask`

        Request body:
            {
                'document_id': @document_id@,
                'lang': @lang@,
                'version_id': @version_id@
            }

        """
        version = _get_version(self.request)
        version.masked = False

        update_cache_version_direct(self.request.validated['document_id'])

        return {}
