import transaction
import logging

from c2corg_api.models import DBSession
from c2corg_api.models.route import Route
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mapping import SearchDocument
from c2corg_api.search.utils import strip_bbcodes, get_title

log = logging.getLogger(__name__)


def run_on_successful_transaction(operation):
    """Run the given operation when the current transaction is committed
    successfully.
    """
    def run_when_successful(success, *args, **kws):
        if success:
            try:
                operation()
            except Exception as exc:
                log.error('Scheduled operation failed', exc)
        else:
            log.info('Scheduled operation is not run because transaction '
                     'was not successful')

    current_transaction = transaction.get()
    current_transaction.addAfterCommitHook(run_when_successful)


def sync_search_index(document):
    """Update the document in ElasticSearch. If the document is not yet present
     in the ElasticSearch index, it will be created.
     The operation will be run once the current transaction has been committed
     successfully.
    """
    if isinstance(document, Route):
        # TODO the locales of routes have to be refreshed because the title
        # prefix is set directly in the database. this is not optimized further
        # because it is going to change anyway with
        # https://github.com/c2corg/v6_api/issues/89
        DBSession.refresh(document)

    document_id = document.document_id
    doc = {
        'doc_type': document.type
    }

    has_title_prefix = isinstance(document, Route)
    for locale in document.locales:
        culture = locale.culture

        # set the title prefix (name of the main waypoint) for routes
        title_prefix = locale.title_prefix if has_title_prefix else None
        title = get_title(locale.title, title_prefix)

        doc['title_' + culture] = title
        doc['summary_' + culture] = strip_bbcodes(locale.summary)
        doc['description_' + culture] = strip_bbcodes(locale.description)

    def sync_operation():
        client = elasticsearch_config['client']
        index_name = elasticsearch_config['index']

        client.index(
            index=index_name,
            doc_type=SearchDocument._doc_type.name,
            id=document_id,
            body=doc
        )

    run_on_successful_transaction(sync_operation)
