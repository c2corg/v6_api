import logging
import time

from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE
from redis.connection import BlockingConnectionPool

log = logging.getLogger(__name__)

# prefix for all cache keys
KEY_PREFIX = 'c2corg'

# cache version (for production the current git revisions, for development
# the git revision and a timestamp).
CACHE_VERSION = None

# the current status (up/down) of the cache
cache_status = None


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
cache_sitemap_xml = create_region('sitemap_xml')

caches = [
    cache_document_cooked,
    cache_document_detail,
    cache_document_listing,
    cache_document_history,
    cache_document_version,
    cache_document_info,
    cache_sitemap,
    cache_sitemap_xml
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
                "thread_local_lock": False,
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


def initialize_cache_status(refresh_period):
    global cache_status
    cache_status = CacheStatus(refresh_period)


def get_or_create(cache, key, creator):
    """ Try to get the value for the given key from the cache. In case of
    errors fallback to the creator function (e.g. load from the database).
    """
    if cache_status.is_down():
        log.warning('Not getting value from cache because it seems to be down')
        return creator()

    try:
        value = cache.get_or_create(
            key, creator_wrapper(creator), expiration_time=-1)
        cache_status.request_success()
        return value
    except CreatorException as creator_exception:
        raise creator_exception.exc
    except Exception:
        log.error('Getting value from cache failed', exc_info=True)
        cache_status.request_failure()
        return creator()


def get_or_create_multi(cache, keys, creator, should_cache_fn=None):
    """ Try to get the values for the given keys from the cache. In case of
    errors fallback to the creator function (e.g. load from the database).
    """
    if cache_status.is_down():
        log.warning('Not getting values from cache since it seems to be down')
        return creator(*keys)

    try:
        values = cache.get_or_create_multi(
            keys, creator_wrapper(creator), expiration_time=-1,
            should_cache_fn=should_cache_fn)
        cache_status.request_success()
        return values
    except CreatorException as creator_exception:
        raise creator_exception.exc
    except Exception:
        log.error('Getting values from cache failed', exc_info=True)
        cache_status.request_failure()
        return creator(*keys)


def get(cache, key):
    """ Try to get the value for the given key from the cache. In case of
    errors, return NO_VALUE.
    """
    if cache_status.is_down():
        log.warning('Not getting value from cache because it seems to be down')
        return NO_VALUE

    try:
        value = cache.get(key, ignore_expiration=True)
        cache_status.request_success()
        return value
    except Exception:
        log.error('Getting value from cache failed', exc_info=True)
        cache_status.request_failure()
        return NO_VALUE


def set(cache, key, value):
    """ Try to set the value with the given key in the cache. In case of
    errors, log the error and continue.
    """
    if cache_status.is_down():
        log.warning('Not setting value in cache because it seems to be down')
        return

    try:
        cache.set(key, value)
        cache_status.request_success()
    except Exception:
        log.error('Setting value in cache failed', exc_info=True)
        cache_status.request_failure()


class CreatorException(Exception):
    """ An exception happening during the execution of a cache `creator`
    function.
    """
    def __init__(self, exc):
        self.exc = exc


def creator_wrapper(creator):
    """ A wrapper around `creator` functions. The purpose of this wrapper is
    to distinguish exceptions caused in creator functions from exceptions
    while trying to read a value from the cache.
    """
    def fn(*args, **kwargs):
        try:
            return creator(*args, **kwargs)
        except Exception as exc:
            raise CreatorException(exc)
    return fn


class CacheStatus(object):
    """ To avoid that requests are made to the cache if it is down, the status
    of the last requests is stored. If a request in the 30 seconds failed,
    no new request will be made.
    """

    def __init__(self, refresh_period=30):
        self.up = True
        self.status_time = time.time()
        self.refresh_period = refresh_period

    def is_down(self):
        if self.up:
            return False

        # no request is made to the cache if it is down. but if the cache
        # status should be refreshed, a request is made even though it was
        # down before.
        should_refresh = time.time() - self.status_time > self.refresh_period
        return not should_refresh

    def request_failure(self):
        self.up = False
        self.status_time = time.time()

    def request_success(self):
        self.up = True
        self.status_time = time.time()
