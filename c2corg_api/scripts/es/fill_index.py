import os
import sys

from c2corg_api.models.route import RouteLocale
from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars
from datetime import datetime, timedelta

from sqlalchemy import engine_from_config

from c2corg_api.search.mapping import SearchDocument
from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import configure_es_from_config, elasticsearch_config
from c2corg_api.search.utils import strip_bbcodes, get_title

batch_size = 1000


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
    configure_es_from_config(settings)
    fill_index(DBSession)


def fill_index(db_session):
    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']

    status = {
        'start_time': datetime.now(),
        'last_progress_update': None
    }

    total = DBSession.query(DocumentLocale).count()

    q = DBSession.query(
            DocumentLocale.document_id, DocumentLocale.title,
            DocumentLocale.summary, DocumentLocale.description,
            DocumentLocale.lang, DocumentLocale.type,
            RouteLocale.__table__.c.title_prefix). \
        outerjoin(
            RouteLocale.__table__,
            DocumentLocale.id == RouteLocale.__table__.c.id).\
        order_by(DocumentLocale.document_id, DocumentLocale.lang)

    def progress(count, total_count):
        if status['last_progress_update'] is None or \
                status['last_progress_update'] + timedelta(seconds=1) < \
                datetime.now():
            print('{0} of {1}'.format(count, total_count))
            status['last_progress_update'] = datetime.now()

    search_document = None
    last_id = None
    batch = ElasticBatch(client, batch_size)
    count = 0
    with batch:
        for document_id, title, summary, description, lang, type, \
                title_prefix in q:
            if search_document is not None and document_id != last_id:
                batch.add(search_document)
                search_document = None

            if search_document is None:
                search_document = {
                    '_op_type': 'index',
                    '_index': index_name,
                    '_type': SearchDocument._doc_type.name,
                    '_id': document_id,
                    'doc_type': type
                }

            search_document['title_' + lang] = get_title(
                title, title_prefix)
            search_document['summary_' + lang] = strip_bbcodes(summary)
            search_document['description_' + lang] = \
                strip_bbcodes(description)

            last_id = document_id
            count += 1
            progress(count, total)

        if search_document is not None:
            batch.add(search_document)

    duration = datetime.now() - status['start_time']
    print('Done (duration: {0})'.format(duration))
