from c2corg_api.search.mapping_types import meta_param_keys
from c2corg_api.search.search_filters import build_query


def get_search_documents(url_params, meta_params, doc_type):
    """Returns a function that when called with a base-query returns all
    document ids that match the search filters given in the URL parameters.
    """
    def search_documents(_, __):
        document_ids, total = search(url_params, meta_params, doc_type)
        return document_ids, total

    return search_documents


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
