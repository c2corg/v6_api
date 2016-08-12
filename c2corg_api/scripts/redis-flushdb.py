""" A script to call `flushdb` on the Redis database that is used as cache.

Note that all keys from the Redis database are deleted. If the database is
shared with other instances or applications, the keys of these will also be
removed.
"""
import logging

import os
import sys

from pyramid.paster import get_appsettings, setup_logging
from pyramid.scripts.common import parse_vars

from redis.client import Redis
from redis.connection import ConnectionPool

log = logging.getLogger('c2corg_api.redis_flushdb')


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    logging.getLogger('c2corg_api').setLevel(logging.INFO)

    redis_url = '{0}?db={1}'.format(
        settings['redis.url'], settings['redis.db_cache'])
    log.info('Cache Redis: {0}'.format(redis_url))

    # we don't really need a connection pool here, but the `from_url`
    # function is convenient
    redis_pool = ConnectionPool.from_url(redis_url, max_connections=1)

    # remove all keys from the database
    r = Redis(connection_pool=redis_pool)
    r.flushdb()
    log.info('Flushed cache')

if __name__ == "__main__":
    main()
