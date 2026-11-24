import logging
import os
import sys

from sqlalchemy import engine_from_config

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.jobs.harvest_partner_outings import harvest_partner_outings
from c2corg_api.models import DBSession

log = logging.getLogger('c2corg_api_harvest_partners')


def usage(argv):
    cmd = os.path.basename(argv[0])
    print(f'usage: {cmd} <config_uri> [var=value]\n(example: "{cmd} development.ini")')
    sys.exit(1)


def main(argv=sys.argv):
    """Harvest the partner outings once (make harvest-partners)."""
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)

    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)

    harvest_partner_outings(settings)


if __name__ == '__main__':
    main()
