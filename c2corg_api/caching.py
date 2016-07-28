import logging
from dogpile.cache import make_region

log = logging.getLogger(__name__)

# prefix for all cache keys
KEY_PREFIX = 'c2corg'


def create_region(name):
    return make_region(
        # prefix all keys (e.g. returns 'c2corg_main:dogpile:38575-1')
        key_mangler=lambda key: KEY_PREFIX + ':dogpile:' + key
    )

cache_document_detail = create_region('detail')
# cache_document_listing = create_region('listing')


def configure_caches(settings):
    global KEY_PREFIX
    KEY_PREFIX = settings['redis.cache_key_prefix']

    log.debug('Redis: {0}'.format(settings['redis.url']))

    # TODO use connection pool
    cache_document_detail.configure(
        'dogpile.cache.redis',
        arguments={
            'url': settings['redis.url'],
            'distributed_lock': True,
            'socket_timeout': 3,  # 3 seconds
            'lock_timeout': 5  # 5 seconds
        },
        replace_existing_backend=True
    )
    cache_document_detail.invalidate()
