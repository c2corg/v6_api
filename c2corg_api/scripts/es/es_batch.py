from elasticsearch import helpers

from c2corg_api.scripts.migration.batch import Batch
from elasticsearch.helpers import BulkIndexError
import logging

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
        super(ElasticBatch, self).__init__(client, batch_size)
        self.client = client
        self.actions = []

    def add(self, action):
        self.actions.append(action)
        self.flush_or_not()

    def should_flush(self):
        return len(self.actions) > self.batch_size

    def flush(self):
        if self.actions:
            try:
                helpers.bulk(self.client, self.actions)
            except BulkIndexError:
                # when trying to delete a document that does not exist, an
                # error is raised, but all other documents are inserted
                log.warn(
                    'error sending bulk update to ElasticSearch',
                    exc_info=True)
            self.actions = []
