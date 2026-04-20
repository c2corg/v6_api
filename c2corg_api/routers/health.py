"""
FastAPI Health router.

Provides ``/v2/health`` — returns status information about the API
and its components (database, ElasticSearch, Redis, maintenance mode).
"""

import logging
from os.path import isfile

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from c2corg_api.caching import cache_document_detail
from c2corg_api.database import get_db
from c2corg_api.models import es_sync
from c2corg_api.search import elasticsearch_config

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['health'])

# Module-level cache — set once by ``configure_health``.
_cache_version: str = ''


def configure_health(settings: dict) -> None:
    """Called once at startup to capture the cache_version setting."""
    global _cache_version
    _cache_version = settings.get('cache_version', '')


@router.get('/health')
def get_health(response: Response, db: Session = Depends(get_db)):
    """Returns information about the version of the API and the status
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
    status = {'version': _cache_version}

    _add_database_status(status, response, db)
    _add_es_status(status, response)
    _add_redis_status(status)
    _add_maintenance_mode_status(status, response)

    return status


def _add_database_status(status, response, db):
    last_es_syncer_run = None
    success = False

    try:
        last_es_syncer_run, _ = es_sync.get_status(db)
        success = True
    except Exception:
        log.exception('Getting last es syncer run failed')
        response.status_code = 500

    status['pg'] = 'ok' if success else 'error'
    status['last_es_syncer_run'] = (
        last_es_syncer_run.isoformat() if last_es_syncer_run else ''
    )


def _add_es_status(status, response):
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
        response.status_code = 500

    status['es'] = 'ok' if success else 'error'
    status['es_indexed_docs'] = es_docs


def _add_redis_status(status):
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


def _add_maintenance_mode_status(status, response):
    maintenance_mode = False
    maintenance_file = 'maintenance_mode.txt'

    if isfile(maintenance_file):
        maintenance_mode = True
        log.warning(
            'service is in maintenance mode, remove %s to reenable.' % maintenance_file
        )
        response.status_code = 404

    status['maintenance_mode'] = maintenance_mode
