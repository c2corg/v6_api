import logging

from c2corg_api.caching import cache_document_detail
from c2corg_api.models import DBSession, es_sync
from c2corg_api.search import elasticsearch_config
from c2corg_api.views import cors_policy
from cornice.resource import resource, view
from os.path import isfile

log = logging.getLogger(__name__)


@resource(path='/health', cors_policy=cors_policy)
class HealthRest(object):

    def __init__(self, request):
        self.request = request

    @view()
    def get(self):
        """ Returns information about the version of the API and the status
        of its components:

            - Git revision
            - PostgreSQL status
            - Last run of the ES syncer script
            - ES status
            - Number of documents indexed in ES
            - Redis status
            - Number of keys in Redis
            - Maintenance mode status

        """
        status = {
            'version': self.request.registry.settings.get('cache_version')
        }

        self._add_database_status(status)
        self._add_es_status(status)
        self._add_redis_status(status)
        self._add_maintenance_mode_status(status)

        return status

    def _add_database_status(self, status):
        last_es_syncer_run = None
        success = False

        try:
            last_es_syncer_run, _ = es_sync.get_status(DBSession)
            success = True
        except Exception:
            log.exception('Getting last es syncer run failed')
            self.request.response.status_code = 500

        status['pg'] = 'ok' if success else 'error'
        status['last_es_syncer_run'] = last_es_syncer_run.isoformat() \
            if last_es_syncer_run else ''

    def _add_es_status(self, status):
        es_docs = None
        success = False

        try:
            client = elasticsearch_config['client']
            index = elasticsearch_config['index']
            stats = client.indices.stats(index, metric='docs')
            es_docs = stats['indices'][index]['total']['docs']['count']
            success = True
        except Exception:
            log.exception('Getting indexed docs count failed')
            self.request.response.status_code = 500

        status['es'] = 'ok' if success else 'error'
        status['es_indexed_docs'] = es_docs

    def _add_redis_status(self, status):
        redis_keys = None
        success = False

        try:
            client = cache_document_detail.backend.client
            redis_keys = client.dbsize()
            success = True
        except Exception:
            log.exception('Getting redis keys failed')

        status['redis'] = 'ok' if success else 'error'
        status['redis_keys'] = redis_keys

    def _add_maintenance_mode_status(self, status):
        maintenance_mode = False
        maintenance_file = 'maintenance_mode.txt'

        if isfile(maintenance_file):
            maintenance_mode = True
            log.warning(
              'service is in maintenance mode, remove %s to reenable.' %
              maintenance_file)
            self.request.response.status_code = 404

        status['maintenance_mode'] = maintenance_mode
