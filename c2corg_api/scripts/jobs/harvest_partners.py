import logging
import os
import sys

from sqlalchemy import engine_from_config

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.jobs.harvest_partner_outings import (
    harvest_partner_outings,
    partners_enabled,
)
from c2corg_api.models import DBSession

log = logging.getLogger('c2corg_api_harvest_partners')


def usage(argv):
    cmd = os.path.basename(argv[0])
    print(
        f'usage: {cmd} <config_uri> [--force] [var=value]\n'
        f'(example: "{cmd} development.ini")\n'
        '--force: run even when partners.enabled is not true'
    )
    sys.exit(1)


def main(argv=sys.argv):
    """Harvest the partner outings once (make harvest-partners)."""
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    force = '--force' in argv[2:]
    options = parse_vars([arg for arg in argv[2:] if arg != '--force'])
    setup_logging(config_uri)

    settings = get_appsettings(config_uri, options=options)
    if not force and not partners_enabled(settings):
        print(
            'partners.enabled is not true: nothing harvested. Set partners_enabled'
            f'="true" (make load-env), or run {os.path.basename(argv[0])} '
            f'{config_uri} --force.',
            file=sys.stderr,
        )
        sys.exit(1)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)

    harvest_partner_outings(settings)


if __name__ == '__main__':
    main()
