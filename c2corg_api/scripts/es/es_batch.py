import logging

from elasticsearch import helpers

from c2corg_api.scripts.es.batch import Batch

log = logging.getLogger(__name__)


class ElasticBatch(Batch):
    """A batch implementation to do bulk inserts for ElasticSearch.

    Example usage:

        batch = ElasticBatch(client, 1000)
        with batch:
            ...
            batch.add({
                '_op_type': 'index',
                '_index': index_name,
                '_type': SearchDocument._doc_type.name,
                '_id': document_id,
                'title': 'Abc'
            })
    """

    def __init__(self, client, batch_size):
        super().__init__(client, batch_size)
        self.client = client
        self.actions = []

    def add(self, action):
        self.actions.append(action)
        self.flush_or_not()

    def should_flush(self):
        return len(self.actions) > self.batch_size

    def flush(self):
        if self.actions:
            # do not raise on failed actions: the helper would raise after the
            # first chunk with a failure and never send the next chunks, so
            # the documents of those chunks were silently never (un)indexed
            _, errors = helpers.bulk(self.client, self.actions, raise_on_error=False)
            failed = [error for error in errors if not _is_missing_delete(error)]
            if failed:
                log.warning(
                    f'{len(failed)} action(s) failed in a bulk update to '
                    f'ElasticSearch, first: {failed[0]}'
                )
            self.actions = []


def _is_missing_delete(error):
    """Tell if a bulk error is the delete of a document not in the index."""
    # deleting a document that is already gone is expected: a sync may read a
    # deleted or merged document more than once
    delete = error.get('delete')
    return delete is not None and delete.get('status') == 404
