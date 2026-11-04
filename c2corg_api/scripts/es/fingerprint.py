"""Fingerprint of the code which builds the Elasticsearch index.

An index built by `fill_es_index` is only valid for the version of the code which
built it (mappings, analyzers, the way documents are serialized). The dev database
publication stores this fingerprint in the Elasticsearch it ships, and the dev
container setup compares it with the one of the checked out code: if they differ,
the index is rebuilt.

Usage: es_index_fingerprint <print|store|check> <config_uri>

  print   prints the fingerprint of the code (no Elasticsearch needed, the config is
          not read)
  store   stores it in the Elasticsearch, next to the index (to run after
          fill_es_index)
  check   exit status 0 if the stored fingerprint is the one of the code, 1 if it
          differs, 2 if there is none
"""

import hashlib
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from elasticsearch.exceptions import NotFoundError

import c2corg_api
from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.search import configure_es_from_config, elasticsearch_config

# Files (relative to the c2corg_api package) which decide what the index contains: its
# mappings and analyzers, the serialization of the documents, and the way the index is
# filled and kept in sync.
SOURCES = (
    'search/__init__.py',
    'search/mapping.py',
    'search/mapping_types.py',
    'search/mappings/*.py',
    'scripts/initializees.py',
    'scripts/es/es_batch.py',
    'scripts/es/fill_index.py',
    'scripts/es/sync.py',
)

META_DOC_TYPE = 'meta'
META_DOC_ID = 'fingerprint'


def compute_fingerprint():
    root = Path(c2corg_api.__file__).parent
    paths = sorted({p for pattern in SOURCES for p in root.glob(pattern)})
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        # same result whatever the line endings of the checkout
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    return digest.hexdigest()


def meta_index_name():
    return f'{elasticsearch_config["index"]}_meta'


def store_fingerprint(client):
    client.index(
        index=meta_index_name(),
        doc_type=META_DOC_TYPE,
        id=META_DOC_ID,
        body={
            'fingerprint': compute_fingerprint(),
            'indexed_at': datetime.now(UTC).isoformat(),
        },
        refresh=True,
    )


def stored_fingerprint(client):
    try:
        doc = client.get(
            index=meta_index_name(), doc_type=META_DOC_TYPE, id=META_DOC_ID
        )
    except NotFoundError:
        return None
    return doc['_source'].get('fingerprint')


def main(argv=sys.argv):
    if len(argv) < 3 or argv[1] not in ('print', 'store', 'check'):
        print(__doc__)
        sys.exit(64)
    command, config_uri = argv[1], argv[2]

    if command == 'print':
        print(compute_fingerprint())
        return

    setup_logging(config_uri)
    logging.getLogger('elasticsearch').setLevel(logging.ERROR)
    settings = get_appsettings(config_uri, options=parse_vars(argv[3:]))
    configure_es_from_config(settings)
    client = elasticsearch_config['client']

    if command == 'store':
        store_fingerprint(client)
        print(f'Fingerprint stored: {compute_fingerprint()[:12]}')
        return

    stored = stored_fingerprint(client)
    if stored is None:
        print('The index has no fingerprint')
        sys.exit(2)
    if stored != compute_fingerprint():
        print(
            'The index was built by another version of the indexing code '
            f'({stored[:12]}, the code is {compute_fingerprint()[:12]})'
        )
        sys.exit(1)
    print(f'The index matches the indexing code ({stored[:12]})')


if __name__ == '__main__':
    main()
