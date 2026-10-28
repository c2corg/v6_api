from c2corg_api.search.mapping_types import meta_param_keys
from c2corg_api.search.search_filters import build_query


def get_search_documents(url_params, meta_params, doc_type):
    """Return a function that searches with the URL parameters.

    Returns a function that when called with a base-query returns all
    document ids that match the search filters given in the URL parameters.
    """

    def search_documents(_, __):
        document_ids, total = search(url_params, meta_params, doc_type)
        return document_ids, total

    return search_documents


def search(url_params, meta_params, doc_type):
    """Search with the URL parameters, return (document_ids, total).

    Builds a query from the URL parameters and return a tuple
    (document_ids, total) received from ElasticSearch.
    """
    query = build_query(url_params, meta_params, doc_type)

    # only request the document ids from ES
    response = query.execute()
    document_ids = [int(doc.meta.id) for doc in response]
    total = response.hits.total

    return document_ids, total


def search_with_ids(url_params, meta_params, doc_type, id_chunk=None):
    """Search with the URL parameters and ids, return (document_ids, total).

    Builds a query from the URL parameters and a list of ids
    and return a tuple (document_ids, total) received from ElasticSearch.
    """
    query = build_query(url_params, meta_params, doc_type)
    search_dict = query.to_dict()

    # Inject a terms filter for the chunk of IDs if provided
    if id_chunk:
        id_chunk_str = [str(document_id) for document_id in id_chunk]
        terms_filter = {'terms': {'_id': id_chunk_str}}
        if 'bool' not in search_dict.get('query', {}):
            search_dict['query'] = {'bool': {'filter': []}}
        elif 'filter' not in search_dict['query']['bool']:
            search_dict['query']['bool']['filter'] = []

        search_dict['query']['bool']['filter'].append(terms_filter)

        search_dict['from'] = 0
        search_dict['size'] = len(id_chunk)

    query.update_from_dict(search_dict)

    response = query.execute()
    document_ids = [int(doc.meta.id) for doc in response]
    total = response.hits.total

    return document_ids, total


def get_filtered_docs_page(params, meta_params, ids, doc_type):
    """Get a page of the docs ids (offset, limit), filtered in ES, and the total."""
    from c2corg_api.views.document import ES_MAX_RESULT_WINDOW

    offset = meta_params.get('offset') or 0
    limit = meta_params.get('limit')
    # one query: ElasticSearch filters, sorts and pages the documents
    query = build_query(params, meta_params, doc_type)
    query = query.filter('terms', _id=[str(doc_id) for doc_id in ids])
    if offset + limit <= ES_MAX_RESULT_WINDOW:
        response = query.execute()
        return [int(doc.meta.id) for doc in response], response.hits.total

    # beyond the result window of ElasticSearch: scroll through the sorted
    # documents up to the end of the page
    doc_ids = []
    scroll = query.extra(from_=0, size=1000).params(preserve_order=True, scroll='1m')
    for hit in scroll.scan():
        doc_ids.append(int(hit.meta.id))
        if len(doc_ids) >= offset + limit:
            break
    total = query.extra(from_=0, size=0).execute().hits.total
    return doc_ids[offset : offset + limit], total


def get_all_filtered_docs(params, meta_params, ids, doc_type):
    """Get all docs ids, taking into account ES filter in params."""
    filtered_doc_ids = []
    total_hits = 0

    # use elastic search to apply filters
    # to documents of type ids
    for _, id_chunk in enumerate(
        chunk_ids(
            ids,
        ),
        start=1,
    ):
        doc_ids, hits = search_with_ids(
            params, meta_params, doc_type=doc_type, id_chunk=id_chunk
        )
        filtered_doc_ids.extend(doc_ids)
        total_hits += hits

    return filtered_doc_ids, total_hits


def chunk_ids(ids_set):
    from c2corg_api.views.document import ES_MAX_RESULT_WINDOW

    """
    Yield successive chunks of IDs from a set/list.
    chunk size is ES_MAX_RESULT_WINDOW
    """
    ids_list = list(ids_set)
    for i in range(0, len(ids_list), ES_MAX_RESULT_WINDOW):
        yield ids_list[i : i + ES_MAX_RESULT_WINDOW]


def contains_search_params(url_params):
    """Check if the URL has parameters other than meta-data ones.

    Checks if the url query string contains other parameters than meta-data
    parameters (like offset, limit, preferred language).
    """
    for param in url_params:
        if param not in meta_param_keys:
            return True
    return False
