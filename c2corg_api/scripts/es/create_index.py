#!/usr/bin/env python
"""
Creates (or recreates) the ES index with the correct mappings.
Must be run before fill_index.py when building the index from scratch.

Usage: python create_index.py <config>.ini
"""
import sys
import logging

from pyramid.paster import get_appsettings, setup_logging
from pyramid.scripts.common import parse_vars

from c2corg_api.search import configure_es_from_config, elasticsearch_config, \
    search_documents
from c2corg_api.search.mapping import analysis_settings


def main(argv=sys.argv):
    if len(argv) < 2:
        print('Usage: %s <config_uri> [var=value]' % argv[0])
        sys.exit(1)

    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

    settings = get_appsettings(config_uri, options=options)
    configure_es_from_config(settings)

    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']

    # Delete index if it exists (to fix potentially wrong mappings)
    if client.indices.exists(index=index_name):
        print('Deleting existing index: {}'.format(index_name))
        client.indices.delete(index=index_name)

    # Create index with analysis settings
    print('Creating index: {}'.format(index_name))
    client.indices.create(index=index_name, body={
        'settings': {
            'analysis': analysis_settings
        }
    })

    # Apply the correct mapping for every document type
    # (if we let ES infer types by directly running fill_index.py,
    # we could run into type errors on some fields like
    # a mapping geom -> double instead of geo_point).
    for doc_type, search_class in search_documents.items():
        print('Applying mapping for doc_type: {}'.format(doc_type))
        search_class._doc_type.mapping.save(index_name)

    print('Done. Index "{}" created with correct mappings.'.format(index_name))
    print('You can now run fill_index.py safely.')


if __name__ == '__main__':
    main()
