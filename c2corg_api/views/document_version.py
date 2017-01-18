from c2corg_api.caching import cache_document_version
from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.user import User
from c2corg_api.views import to_json_dict, etag_cache
from c2corg_common.utils.caching import get_or_create
from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import union


class DocumentVersionRest(object):
    """ Base class for all views that return a specific version of a document.
    """

    def __init__(self, request):
        self.request = request

    def _get_version(self, clazz, locale_clazz, schema, adapt_schema=None):
        document_id = self.request.validated['id']
        lang = self.request.validated['lang']
        version_id = self.request.validated['version_id']

        def create_response():
            return self._load_version(
                document_id, lang, version_id, clazz, locale_clazz, schema,
                adapt_schema)

        base_cache_key = get_cache_key(document_id, lang)
        if not base_cache_key:
            raise HTTPNotFound(
                'no version for document {0}'.format(document_id))
        else:
            cache_key = '{0}-{1}'.format(base_cache_key, version_id)
            # set and check the etag: if the etag value provided in the
            # request equals the current etag, return 'NotModified'
            etag_cache(self.request, cache_key)

            return get_or_create(
                cache_document_version, cache_key, create_response)

    def _load_version(
            self, document_id, lang, version_id, clazz, locale_clazz, schema,
            adapt_schema):
        version = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user').
                     load_only(User.id, User.name)) \
            .options(joinedload(
                DocumentVersion.document_archive.of_type(clazz))) \
            .options(joinedload(
                DocumentVersion.document_locales_archive.of_type(
                    locale_clazz))) \
            .options(joinedload(DocumentVersion.document_geometry_archive)) \
            .filter(DocumentVersion.id == version_id) \
            .filter(DocumentVersion.document_id == document_id) \
            .filter(DocumentVersion.lang == lang) \
            .first()
        if version is None:
            raise HTTPNotFound('invalid version')

        archive_document = version.document_archive
        archive_document.geometry = version.document_geometry_archive
        archive_document.locales = [version.document_locales_archive]

        if adapt_schema:
            schema = adapt_schema(schema, archive_document)

        previous_version_id, next_version_id = get_neighbour_version_ids(
            version_id, document_id, lang
        )

        return {
            'document': to_json_dict(archive_document, schema),
            'version': serialize_version(version),
            'previous_version_id': previous_version_id,
            'next_version_id': next_version_id,
        }


def serialize_version(version):
    return {
        'version_id': version.id,
        'user_id': version.history_metadata.user_id,
        'name': version.history_metadata.user.name,
        'comment': version.history_metadata.comment,
        'written_at': version.history_metadata.written_at.isoformat()
    }


def get_neighbour_version_ids(version_id, document_id, lang):
    """
    Get the previous and next version for a version of a document with a
    specific language.
    """
    next_version = DBSession \
        .query(
            DocumentVersion.id.label('id'),
            literal_column('1').label('t')) \
        .filter(DocumentVersion.id > version_id) \
        .filter(DocumentVersion.document_id == document_id) \
        .filter(DocumentVersion.lang == lang) \
        .order_by(DocumentVersion.id) \
        .limit(1) \
        .subquery()

    previous_version = DBSession \
        .query(
            DocumentVersion.id.label('id'),
            literal_column('-1').label('t')) \
        .filter(DocumentVersion.id < version_id) \
        .filter(DocumentVersion.document_id == document_id) \
        .filter(DocumentVersion.lang == lang) \
        .order_by(DocumentVersion.id.desc()) \
        .limit(1) \
        .subquery()

    query = DBSession \
        .query('id', 't') \
        .select_from(union(
            next_version.select(), previous_version.select()))

    previous_version_id = None
    next_version_id = None
    for version, typ in query:
        if typ == -1:
            previous_version_id = version
        else:
            next_version_id = version

    return previous_version_id, next_version_id
