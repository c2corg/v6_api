#!/usr/bin/env python
"""Creates (or recreates) the ES indices with the correct mappings.

Must be run before fill_index.py when building the index from scratch.

Usage: python create_index.py <config>.ini
"""

import logging
import sys

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.scripts import initializees
from c2corg_api.search import configure_es_from_config


def main(argv=sys.argv):
    if len(argv) < 2:
        print(f'Usage: {argv[0]} <config_uri> [var=value]')
        sys.exit(1)

    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

    settings = get_appsettings(config_uri, options=options)
    configure_es_from_config(settings)

    # Delete the indices if they exist (to fix potentially wrong mappings)
    print('Deleting the existing indices')
    initializees.drop_index(silent=False)

    # Create the indices with the analysis settings and the correct mapping for
    # every document type (if we let ES infer types by directly running
    # fill_index.py, we could run into type errors on some fields like
    # a mapping geom -> double instead of geo_point).
    initializees.setup_es()

    print('Done. The indices are created with the correct mappings.')
    print('You can now run fill_index.py safely.')


if __name__ == '__main__':
    main()
