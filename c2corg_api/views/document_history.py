from c2corg_api.caching import cache_document_history
from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import DocumentLocale, DOCUMENT_TYPE
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.views import cors_policy, etag_cache
from c2corg_api.views.document_version import serialize_version
from c2corg_api.views.validation import validate_lang, validate_id
from c2corg_api.caching import get_or_create
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.orm import joinedload


@resource(path='/document/{id}/history/{lang}', cors_policy=cors_policy)
class HistoryDocumentRest(object):
    """ Unique class for returning history of a document.
    """

    def __init__(self, request):
        self.request = request

    @view(validators=[validate_id, validate_lang])
    def get(self):
        document_id = self.request.validated['id']
        lang = self.request.validated['lang']

        def create_response():
            return self._get_history(document_id, lang)

        # history entry point does no precise document type.
        cache_key = get_cache_key(
            document_id,
            lang,
            document_type=DOCUMENT_TYPE)

        if not cache_key:
            raise HTTPNotFound(
                'no version for document {0}'.format(document_id))
        else:
            # set and check the etag: if the etag value provided in the
            # request equals the current etag, return 'NotModified'
            etag_cache(self.request, cache_key)

            return get_or_create(
                cache_document_history, cache_key, create_response)

    def _get_history(self, document_id, lang):
        # FIXME conditional permission check (when outings implemented)
        # is_outing = DBSession.query(Outing) \
        #       .filter(Outing.document_id == document_id).count()
        # if is_outing > 0:
        #    # validate permission (authenticated + associated)
        #    # return 403 if not correct

        title = DBSession.query(DocumentLocale.title) \
            .filter(DocumentLocale.document_id == document_id) \
            .filter(DocumentLocale.lang == lang) \
            .first()

        if not title:
            raise HTTPNotFound('no locale document for "{0}"'.format(lang))

        versions = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user')) \
            .filter(DocumentVersion.document_id == document_id) \
            .filter(DocumentVersion.lang == lang) \
            .order_by(DocumentVersion.id) \
            .all()

        return {
            'title': title.title,
            'versions': [serialize_version(v) for v in versions]
        }
