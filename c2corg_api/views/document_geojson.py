import logging

from c2corg_api.models import DBSession

log = logging.getLogger(__name__)


class DocumentGeojsonRest(object):
    """ Base class for GeoJSON-formatted list services.
    """

    def __init__(self, request):
        self.request = request

    def _get_documents(self, doc_type):
        validated = self.request.validated
        meta_params = {
            'bbox': validated.get('bbox'),
            'lang': validated.get('lang')
        }

        #query = DBSession.query(
        
        return {
            'todo': True
        }
