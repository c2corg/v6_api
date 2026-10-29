import logging

from sqlalchemy.sql.expression import and_, exists

from c2corg_api import DBSession
from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int, OneOf
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import restricted_json_view
from c2corg_api.views.resource import resource

log = logging.getLogger(__name__)


class MaskSchema(Schema):
    document_id: Int
    lang: OneOf(default_langs)
    version_id: Int


def validate_version(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']
    version_id = request.validated['version_id']

    # check the version to mask/unmask actually exists
    version_exists = DBSession.query(
        exists().where(
            and_(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.lang == lang,
            )
        )
    ).scalar()
    if not version_exists:
        raise HTTPBadRequest(f'Unknown version {document_id}/{lang}/{version_id}')

    # check the version to mask/unmask is not the latest one
    (latest_version_id,) = (
        DBSession.query(DocumentVersion.id)
        .filter(
            and_(
                DocumentVersion.document_id == document_id, DocumentVersion.lang == lang
            )
        )
        .order_by(DocumentVersion.id.desc())
        .first()
    )
    if version_id == latest_version_id:
        raise HTTPBadRequest(
            f'Version {document_id}/{lang}/{version_id} is the latest one'
        )


def _get_version(request):
    document_id = request.validated['document_id']
    lang = request.validated['lang']
    version_id = request.validated['version_id']

    version = DBSession.get(DocumentVersion, version_id)

    if not version:
        raise HTTPBadRequest(f'Unknown version_id {version_id}')

    if version.document_id != document_id or version.lang != lang:
        raise HTTPBadRequest(f'Unknown version {document_id}/{lang}/{version_id}')

    return version


@resource(path='/versions/mask')
class VersionMaskRest(ACLDefault):
    @restricted_json_view(
        permission='moderator',
        validators=[body_validator(MaskSchema), validate_version],
    )
    def post(self):
        """Mask the given document version.

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


@resource(path='/versions/unmask')
class VersionUnmaskRest(ACLDefault):
    @restricted_json_view(
        permission='moderator',
        validators=[body_validator(MaskSchema), validate_version],
    )
    def post(self):
        """Unmask the given version.

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
