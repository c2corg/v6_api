import os
import sys

import transaction
from c2corg_api.models.route import RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars
from datetime import datetime, timedelta

from sqlalchemy import engine_from_config

from c2corg_api.models import es_sync
from c2corg_api.models.document import DocumentLocale, Document
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import configure_es_from_config, elasticsearch_config, \
    batch_size
from c2corg_api.search.utils import strip_bbcodes, get_title
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

    total = session.query(DocumentLocale). \
        join(Document).filter(Document.redirects_to.is_(None)).count()

    q = session.query(
            DocumentLocale.document_id, DocumentLocale.title,
            DocumentLocale.summary, DocumentLocale.description,
            DocumentLocale.lang, Document.type,
            RouteLocale.__table__.c.title_prefix,
            User.name, User.username). \
        join(Document).filter(Document.redirects_to.is_(None)). \
        outerjoin(
            RouteLocale.__table__,
            DocumentLocale.id == RouteLocale.__table__.c.id).\
        outerjoin(
            User,
            DocumentLocale.document_id == User.id).\
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
                title_prefix, user_login, user_name in q:
            if search_document is not None and document_id != last_id:
                batch.add(search_document)
                search_document = None

            if search_document is None:
                search_document = {
                    '_op_type': 'index',
                    '_index': index_name,
                    '_type': type,
                    '_id': document_id,
                    'doc_type': type
                }

            if type == USERPROFILE_TYPE:
                # set user login + full-name as document title so that it can
                # be searched
                title = '{0} {1}'.format(user_name or '', user_login or '')

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

    es_sync.mark_as_updated(session, date_now)

    duration = datetime.now() - status['start_time']
    print('Done (duration: {0})'.format(duration))
