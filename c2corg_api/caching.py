import logging
from dogpile.cache import make_region
from redis.connection import BlockingConnectionPool

log = logging.getLogger(__name__)

# prefix for all cache keys
KEY_PREFIX = 'c2corg'


def create_region(name):
    return make_region(
        # prefix all keys (e.g. returns 'c2corg_main:detail:38575-1')
        key_mangler=lambda key: '{0}:{1}:{2}'.format(KEY_PREFIX, name, key)
    )

cache_document_detail = create_region('detail')
cache_document_listing = create_region('listing')
cache_document_history = create_region('history')
cache_document_version = create_region('version')

caches = [
    cache_document_detail,
    cache_document_listing,
    cache_document_history,
    cache_document_version
]


def configure_caches(settings):
    global KEY_PREFIX
    KEY_PREFIX = settings['redis.cache_key_prefix']

    log.debug('Cache Redis: {0}'.format(settings['redis.url']))

    redis_pool = BlockingConnectionPool.from_url(
        settings['redis.url'],
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
