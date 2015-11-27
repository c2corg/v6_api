import transaction
import logging

from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mapping import SearchDocument

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
    document_id = document.document_id
    doc = {
        'doc_type': document.type
    }
    for locale in document.locales:
        culture = locale.culture
        doc['title_' + culture] = locale.title
        doc['summary_' + culture] = locale.summary
        doc['description_' + culture] = locale.description

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
