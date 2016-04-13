import os
import sys

import transaction
from c2corg_api.scripts.es import sync
from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars
from datetime import datetime, timedelta

from sqlalchemy import engine_from_config

from c2corg_api.models import es_sync, document_types
from c2corg_api.models.document import Document
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import configure_es_from_config, elasticsearch_config, \
    batch_size, search_documents
from sqlalchemy.orm.session import sessionmaker
from zope.sqlalchemy.datamanager import ZopeTransactionExtension


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
    Session = sessionmaker(extension=ZopeTransactionExtension())  # noqa
    session = Session(bind=engine)
    configure_es_from_config(settings)

    with transaction.manager:
        fill_index(session)


def fill_index(session):
    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']

    status = {
        'start_time': datetime.now(),
        'last_progress_update': None
    }

    _, date_now = es_sync.get_status(session)

    total = session.query(Document). \
        filter(Document.redirects_to.is_(None)).count()

    def progress(count, total_count):
        if status['last_progress_update'] is None or \
                status['last_progress_update'] + timedelta(seconds=1) < \
                datetime.now():
            print('{0} of {1}'.format(count, total_count))
            status['last_progress_update'] = datetime.now()

    batch = ElasticBatch(client, batch_size)
    count = 0
    with batch:
        for doc_type in document_types:
            print('Importing document type {}'.format(doc_type))
            to_search_document = search_documents[doc_type].to_search_document

            for doc in sync.get_documents(session, doc_type):
                batch.add(to_search_document(doc, index_name))

                count += 1
                progress(count, total)

    es_sync.mark_as_updated(session, date_now)

    duration = datetime.now() - status['start_time']
    print('Done (duration: {0})'.format(duration))
