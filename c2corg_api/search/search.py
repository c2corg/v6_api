from c2corg_api.search import create_search, elasticsearch_config, \
    get_text_query_on_title
from c2corg_api.views.document import DocumentRest
from elasticsearch_dsl.search import MultiSearch


def search_for_types(search_types, search_term, limit, lang):
    """Get results for all given types.
    """
    if not search_types:
        return {}

    document_id = try_to_parse_document_id(search_term)

    if document_id is not None:
        # search by document id for every type
        results_for_type = [([document_id], None)] * len(search_types)
    else:
        # search in ElasticSearch
        results_for_type = do_multi_search_for_types(
            search_types, search_term, limit, lang)

    # load the documents using the document ids returned from the search
    results = {}
    for search_type, result_for_type in zip(search_types, results_for_type):
        (key, get_documents_config) = search_type
        (document_ids, total) = result_for_type

        def search_documents(_, __):
            return document_ids, total

        results[key] = DocumentRest.get_documents(
            get_documents_config, {'lang': lang}, search_documents)

    return results


def do_multi_search_for_types(search_types, search_term, limit, lang):
    """ Executes a multi-search for all document types in a single request
    and returns a list of tuples (document_ids, total) containing the results
    for each type.
    """
    multi_search = MultiSearch(index=elasticsearch_config['index'])

    for search_type in search_types:
        (_, get_documents_config) = search_type
        search = create_search(get_documents_config.document_type).\
            query(get_text_query_on_title(search_term, lang)).\
            fields([]).\
            extra(from_=0, size=limit)
        multi_search = multi_search.add(search)

    responses = multi_search.execute()

    results_for_type = []
    for response in responses:
        # only requesting the document ids from ES
        document_ids = [int(doc.meta.id) for doc in response]
        total = response.hits.total
        results_for_type.append((document_ids, total))
    return results_for_type


def try_to_parse_document_id(search_term):
    try:
        return int(search_term)
    except ValueError:
        return None
