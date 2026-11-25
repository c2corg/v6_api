from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import elasticsearch_config, index_name


def test_flush_goes_on_after_a_missing_delete():
    """Index every document of a batch, even after deleting a missing one."""
    # the bulk helper sends the actions in chunks of 500: it used to raise
    # after the first chunk with a failed action and drop the next chunks
    client = elasticsearch_config['client']
    index = index_name('w')
    ids = range(990001, 990601)
    batch = ElasticBatch(client, 1000)
    with batch:
        batch.add({'_op_type': 'delete', '_index': index, '_id': 990000})
        for document_id in ids:
            batch.add(
                {
                    '_op_type': 'index',
                    '_index': index,
                    '_id': document_id,
                    'id': document_id,
                    'c2corg_doc_type': 'w',
                }
            )
    client.indices.refresh(index=index)

    try:
        found = client.mget(
            index=index,
            ids=[str(i) for i in ids],
            source=False,
        )
        assert all(doc['found'] for doc in found['docs'])
    finally:
        batch = ElasticBatch(client, 1000)
        with batch:
            for document_id in ids:
                batch.add(
                    {
                        '_op_type': 'delete',
                        '_index': index,
                        '_id': document_id,
                    }
                )
        client.indices.refresh(index=index)
