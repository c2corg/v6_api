import logging
import time

from c2corg_common.utils.caching import initialize_cache_status
from dogpile.cache import make_region
from redis.connection import BlockingConnectionPool

log = logging.getLogger(__name__)

# prefix for all cache keys
KEY_PREFIX = 'c2corg'

# cache version (for production the current git revisions, for development
# the git revision and a timestamp).
CACHE_VERSION = None


def create_region(name):
    return make_region(
        # prefix all keys (e.g. returns 'c2corg_main:detail:38575-1')
        key_mangler=lambda key: '{0}:{1}:{2}'.format(KEY_PREFIX, name, key)
    )

cache_document_cooked = create_region('cooked')
cache_document_detail = create_region('detail')
cache_document_listing = create_region('listing')
cache_document_history = create_region('history')
cache_document_version = create_region('version')
cache_document_info = create_region('info')
cache_sitemap = create_region('sitemap')

caches = [
    cache_document_cooked,
    cache_document_detail,
    cache_document_listing,
    cache_document_history,
    cache_document_version,
    cache_document_info,
    cache_sitemap
]


def configure_caches(settings):
    global KEY_PREFIX
    global CACHE_VERSION
    global cache_status
    KEY_PREFIX = settings['redis.cache_key_prefix']

    # append a timestamp to the cache key when running in dev. mode
    # (to make sure that the cache values are invalidated when the dev.
    # server reloads when the code changes)
    cache_version = settings['cache_version']
    if settings['cache_version_timestamp'] == 'True':
        cache_version = '{0}-{1}'.format(cache_version, int(time.time()))
    CACHE_VERSION = cache_version

    log.debug('Cache version {0}'.format(CACHE_VERSION))

    redis_url = '{0}?db={1}'.format(
        settings['redis.url'], settings['redis.db_cache'])
    log.debug('Cache Redis: {0}'.format(redis_url))

    redis_pool = BlockingConnectionPool.from_url(
        redis_url,
        max_connections=int(settings['redis.cache_pool']),
        socket_connect_timeout=float(settings['redis.socket_connect_timeout']),
        socket_timeout=float(settings['redis.socket_timeout']),
        timeout=float(settings['redis.pool_timeout'])
    )

    for cache in caches:
        cache.configure(
            'dogpile.cache.redis',
            arguments={
                'connection_pool': redis_pool,
                'distributed_lock': True,
                'lock_timeout': 15,  # 15 seconds (dogpile lock)
                'redis_expiration_time': int(settings['redis.expiration_time'])
            },
            replace_existing_backend=True
        )

    if settings.get('redis.cache_status_refresh_period'):
        refresh_period = int(settings['redis.cache_status_refresh_period'])
    else:
        refresh_period = 30
    initialize_cache_status(refresh_period)
