import logging
import time
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

cache_document_detail = create_region('detail')
cache_document_listing = create_region('listing')
cache_document_history = create_region('history')
cache_document_version = create_region('version')
cache_document_info = create_region('info')

caches = [
    cache_document_detail,
    cache_document_listing,
    cache_document_history,
    cache_document_version,
    cache_document_info
]


def configure_caches(settings):
    global KEY_PREFIX
    global CACHE_VERSION
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
        timeout=3,  # 3 seconds (waiting for connection)
        socket_timeout=3  # 3 seconds (timeout on open socket)
    )

    for cache in caches:
        cache.configure(
            'dogpile.cache.redis',
            arguments={
                'connection_pool': redis_pool,
                'distributed_lock': True,
                'lock_timeout': 5  # 5 seconds (dogpile lock)
            },
            replace_existing_backend=True
        )
        cache.invalidate()
