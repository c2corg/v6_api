"""A script to call `flushdb` on the Redis database that is used as cache.

Note that all keys from the Redis database are deleted. If the database is
shared with other instances or applications, the keys of these will also be
removed.
"""

import logging
import os
import sys

from redis.client import Redis
from redis.connection import ConnectionPool

from c2corg_api.config import get_appsettings, parse_vars, setup_logging

log = logging.getLogger('c2corg_api.redis_flushdb')


def usage(argv):
    cmd = os.path.basename(argv[0])
    print(f'usage: {cmd} <config_uri> [var=value]\n(example: "{cmd} development.ini")')
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    logging.getLogger('c2corg_api').setLevel(logging.INFO)

    redis_url = '{}?db={}'.format(settings['redis.url'], settings['redis.db_cache'])
    log.info(f'Cache Redis: {redis_url}')

    # we don't really need a connection pool here, but the `from_url`
    # function is convenient
    redis_pool = ConnectionPool.from_url(redis_url, max_connections=1)

    # remove all keys from the database
    r = Redis(connection_pool=redis_pool)
    r.flushdb()
    log.info('Flushed cache')


if __name__ == '__main__':
    main()
