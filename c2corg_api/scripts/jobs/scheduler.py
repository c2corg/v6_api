import logging
import sys
import os
import signal

from pyramid.scripts.common import parse_vars
from pyramid.paster import get_appsettings, setup_logging

from sqlalchemy import engine_from_config

from c2corg_api.models import Base, DBSession
from c2corg_api.jobs import configure_scheduler_from_config

log = logging.getLogger('c2corg_api_background_jobs')


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
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    configure_scheduler_from_config(settings)

    signal.pause()

if __name__ == "__main__":
    main()
