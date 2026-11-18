import json
import os
import sys
from pathlib import Path

from c2corg_api.config import (
    get_appsettings,
    parse_vars,
    setup_logging,
)
from c2corg_api.search import (
    configure_es_from_config,
    elasticsearch_config,
    index_name,
    search_documents,
)

# the settings (analyzers) and the mapping of each document type, applied to
# the index of the document type
ES_MAPPINGS_DIR = Path(__file__).resolve().parent.parent / 'search' / 'es_mappings'


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
    configure_es_from_config(settings)
    setup_es()


def _load(name):
    return json.loads((ES_MAPPINGS_DIR / f'{name}.json').read_text(encoding='utf-8'))


def setup_es():
    """Create the ElasticSearch indices (one per document type) and their mapping."""
    client = elasticsearch_config['client']

    info = client.info()
    print('ElasticSearch version: {}'.format(info['version']['number']))

    existing = [
        name
        for name in map(index_name, search_documents)
        if client.indices.exists(index=name)
    ]
    if existing:
        print(
            'Indices already exist: {}. To re-create them, manually delete them '
            'and run this script again.'.format(', '.join(existing))
        )
        print('To delete an index run:')
        print(
            "curl -XDELETE 'http://{}:{}/{}'".format(
                elasticsearch_config['host'], elasticsearch_config['port'], existing[0]
            )
        )
        sys.exit(0)

    for doc_type in search_documents:
        name = index_name(doc_type)
        create_type_index(client, name, doc_type)
        print(f'Index "{name}" created')


def create_type_index(client, name, doc_type, extra_settings=None):
    """Create the index `name` with the settings and the mapping of a document type.

    `extra_settings` are added to the analyzers (`index_management` uses them to
    tune an index for the initial import).
    """
    settings = {**_load('settings'), **(extra_settings or {})}
    client.indices.create(index=name, settings=settings, mappings=_load(doc_type))


def drop_index(silent=True):
    """Remove the ElasticSearch indices."""
    client = elasticsearch_config['client']
    try:
        # one by one: ES refuses to delete indices with a wildcard
        for doc_type in search_documents:
            client.indices.delete(index=index_name(doc_type), ignore_unavailable=True)
    except Exception as exc:
        if not silent:
            raise exc
