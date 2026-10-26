"""The health check: the API version and the status of its components."""
# The load balancer probes it (HEAD /health) and takes a server out of the
# pool while it answers 404: that is the maintenance mode, entered by
# creating the file maintenance_mode.txt in the working directory.

import logging
from os.path import isfile

from fastapi import Request, Response

from c2corg_api.caching import cache_document_detail
from c2corg_api.models import es_sync
from c2corg_api.search import elasticsearch_config
from c2corg_api.web.db import request_session

log = logging.getLogger(__name__)

MAINTENANCE_FILE = 'maintenance_mode.txt'


def include(app):
    """Add the routes of this module to the FastAPI application."""
    # routes are added to the application itself rather than through an
    # APIRouter, which FastAPI keeps nested: the dispatcher and the CORS
    # middleware read the route list
    app.add_api_route('/health', health, methods=['GET', 'HEAD'])


def health(request: Request, response: Response):
    """Return the API version and the status of its components."""
    # the git revision, PostgreSQL, the last run of the ES syncer, ES and its
    # number of documents, Redis and its number of keys, the maintenance mode
    status = {'version': request.app.state.settings.get('cache_version')}
    with request_session() as session:
        if not _add_database_status(status, session):
            response.status_code = 500
    if not _add_es_status(status):
        response.status_code = 500
    _add_redis_status(status)
    if _add_maintenance_mode_status(status):
        response.status_code = 404
    return status


def _add_database_status(status, session):
    last_es_syncer_run = None
    success = False
    try:
        last_es_syncer_run, _ = es_sync.get_status(session)
        success = True
    except Exception:
        log.exception('Getting last es syncer run failed')
    status['pg'] = 'ok' if success else 'error'
    status['last_es_syncer_run'] = (
        last_es_syncer_run.isoformat() if last_es_syncer_run else ''
    )
    return success


def _add_es_status(status):
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
    status['es'] = 'ok' if success else 'error'
    status['es_indexed_docs'] = es_docs
    return success


def _add_redis_status(status):
    # a Redis failure does not fail the health check
    redis_keys = None
    success = False
    try:
        client = cache_document_detail.backend.writer_client
        redis_keys = client.dbsize()
        success = True
    except Exception:
        log.exception('Getting redis keys failed')
    status['redis'] = 'ok' if success else 'error'
    status['redis_keys'] = redis_keys


def _add_maintenance_mode_status(status):
    maintenance_mode = isfile(MAINTENANCE_FILE)
    if maintenance_mode:
        log.warning(
            f'service is in maintenance mode, remove {MAINTENANCE_FILE} to reenable.'
        )
    status['maintenance_mode'] = maintenance_mode
    return maintenance_mode
