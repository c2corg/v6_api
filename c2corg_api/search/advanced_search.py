from c2corg_api.search.mapping_types import meta_param_keys
from c2corg_api.search.search_filters import build_query


def get_load_documents(url_params, meta_params, doc_type, clazz):
    """Returns a function that when called with a base-query returns all
    documents that match the search filters given in the URL parameters.
    """
    document_ids, total = search(url_params, meta_params, doc_type)

    def load_documents(base_query, _):
        if not document_ids:
            return [], total

        documents = base_query. \
            filter(clazz.document_id.in_(document_ids)).\
            all()

        # make sure the documents are returned in the order ES returned them
        document_index = {doc.document_id: doc for doc in documents}
        documents = [
            document_index[id] for id in document_ids if id in document_index]

        return documents, total

    return load_documents


def search(url_params, meta_params, doc_type):
    """Builds a query from the URL parameters and return a tuple
    (document_ids, total) received from ElasticSearch.
    """
    query = build_query(url_params, meta_params, doc_type)

    # only request the document ids from ES
    response = query.execute()
    document_ids = [int(doc.meta.id) for doc in response]
    total = response.hits.total

    return document_ids, total


def contains_search_params(url_params):
    """Checks if the url query string contains other parameters than meta-data
    parameters (like offset, limit, preferred language).
    """
    for param in url_params:
        if param not in meta_param_keys:
            return True
    return False
