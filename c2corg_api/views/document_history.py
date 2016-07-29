from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.views import cors_policy
from c2corg_api.views.document_version import serialize_version
from c2corg_api.views.validation import validate_lang, validate_id
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
        id = self.request.validated['id']
        lang = self.request.validated['lang']

        # FIXME conditional permission check (when outings implemented)
        # is_outing = DBSession.query(Outing) \
        #       .filter(Outing.document_id == id).count()
        # if is_outing > 0:
        #    # validate permission (authenticated + associated)
        #    # return 403 if not correct

        title = DBSession.query(DocumentLocale.title) \
            .filter(DocumentLocale.document_id == id) \
            .filter(DocumentLocale.lang == lang) \
            .first()

        if not title:
            raise HTTPNotFound('no locale document for ' + lang)

        versions = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user')) \
            .filter(DocumentVersion.document_id == id) \
            .filter(DocumentVersion.lang == lang) \
            .order_by(DocumentVersion.id) \
            .all()

        return {
            'title': title.title,
            'versions': [serialize_version(v) for v in versions]
        }
