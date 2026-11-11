import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import transaction
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import sessionmaker
from zope.sqlalchemy import register

from c2corg_api.config import (
    get_appsettings,
    parse_vars,
    setup_logging,
)
from c2corg_api.models import document_types, es_sync
from c2corg_api.models.document import Document
from c2corg_api.scripts.es import sync
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import (
    configure_es_from_config,
    elasticsearch_config,
    search_documents,
)


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
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    Session = sessionmaker()  # noqa
    register(Session)
    session = Session(bind=engine)
    configure_es_from_config(settings)

    batch_size = int(settings.get('elasticsearch.batch_size.fill_index', 1000))

    with transaction.manager:
        fill_index(session, batch_size)


class FillResult(NamedTuple):
    # number of documents sent to ElasticSearch
    count: int
    # database time taken before reading the documents: everything modified
    # since then has to be replayed by the syncer
    sync_date: datetime


def fill_index(session, batch_size=1000, index_name=None, mark_updated=True):
    """Index every document.

    By default the configured index is filled in place. `index_name` targets
    another index (see `reindex.py`). `mark_updated=False` leaves the sync
    status untouched, the caller then has to call `es_sync.mark_as_updated`
    with the returned `sync_date` once the index is actually in use.
    """
    client = elasticsearch_config['client']
    index_name = index_name or elasticsearch_config['index']

    status = {'start_time': datetime.now(UTC), 'last_progress_update': None}

    _, date_now = es_sync.get_status(session)

    total = session.query(Document).filter(Document.redirects_to.is_(None)).count()

    def progress(count, total_count):
        if status['last_progress_update'] is None or status[
            'last_progress_update'
        ] + timedelta(seconds=1) < datetime.now(UTC):
            print(f'{count} of {total_count}')
            status['last_progress_update'] = datetime.now(UTC)

    batch = ElasticBatch(client, batch_size)
    count = 0
    with batch:
        for doc_type in document_types:
            if doc_type not in search_documents:
                # some document types (e.g. coverages) are not indexed
                logging.warning(f'Document type {doc_type} is not indexed')
                continue

            logging.info(f'Importing document type {doc_type}')
            to_search_document = search_documents[doc_type].to_search_document

            for doc in sync.get_documents(
                session, doc_type, batch_size, ignore_redirects=True
            ):
                batch.add(to_search_document(doc, index_name))

                count += 1
                progress(count, total)

    if mark_updated:
        es_sync.mark_as_updated(session, date_now)

    duration = datetime.now(UTC) - status['start_time']
    print(f'Done (duration: {duration})')
    return FillResult(count, date_now)


if __name__ == '__main__':
    main()
