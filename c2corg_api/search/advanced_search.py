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


def search_with_ids(url_params, meta_params, doc_type, id_chunk=None):
    """Builds a query from the URL parameters and a list of ids
    and return a tuple (document_ids, total) received from ElasticSearch.
    """
    query = build_query(url_params, meta_params, doc_type)
    search_dict = query.to_dict()

    # Inject a terms filter for the chunk of IDs if provided
    if id_chunk:
        id_chunk_str = [str(document_id) for document_id in id_chunk]
        terms_filter = {"terms": {"_id": id_chunk_str}}
        if "bool" not in search_dict.get("query", {}):
            search_dict["query"] = {"bool": {"filter": []}}
        elif "filter" not in search_dict["query"]["bool"]:
            search_dict["query"]["bool"]["filter"] = []

        search_dict["query"]["bool"]["filter"].append(terms_filter)
    query.update_from_dict(search_dict)

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
