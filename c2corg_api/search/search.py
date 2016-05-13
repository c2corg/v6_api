from c2corg_api.views.document import add_load_for_profiles
from elasticsearch_dsl.search import MultiSearch
from sqlalchemy.orm import joinedload

from c2corg_api.models import DBSession
from c2corg_api.search import create_search, get_text_query, \
    elasticsearch_config
from c2corg_api.views import to_json_dict, set_best_locale


def search_for_types(search_types, search_term, limit, lang):
    """Get results for all given types.
    """
    document_id = try_to_parse_document_id(search_term)

    if document_id is not None:
        # search by document id for every type
        results_for_type = [([document_id], None)] * len(search_types)
    else:
        # search in ElasticSearch
        results_for_type = do_multi_search_for_types(
            search_types, search_term, limit)

    # load the documents using the document ids returned from the search
    results = {}
    for search_type, result_for_type in zip(search_types, results_for_type):
        (key, document_type, model, locale_model, schema, adapt_schema) = \
            search_type
        (document_ids, total) = result_for_type

        documents = get_documents(document_ids, model, locale_model, lang)
        count = len(documents)
        total = total if total is not None else count

        results[key] = {
            'count': count,
            'total': total,
            'documents': [
                to_json_dict(
                    doc,
                    schema if not adapt_schema else adapt_schema(schema, doc)
                ) for doc in documents
            ]
        }

    return results


def do_multi_search_for_types(search_types, search_term, limit):
    """ Executes a multi-search for all document types in a single request
    and returns a list of tuples (document_ids, total) containing the results
    for each type.
    """
    multi_search = MultiSearch(index=elasticsearch_config['index'])

    for search_type in search_types:
        (_, document_type, _, _, _, _) = search_type
        search = create_search(document_type).\
            query(get_text_query(search_term)).\
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


def get_documents(document_ids, model, locale_model, lang):
    """Load the documents for the given ids.
    The documents are returned in the same order as the ids. If a document
    for a given id does not exist, the document is skipped.
    """
    if not document_ids:
        return []

    documents_query = DBSession.\
        query(model).\
        filter(model.redirects_to.is_(None)).\
        filter(model.document_id.in_(document_ids)).\
        options(joinedload(model.locales.of_type(locale_model))). \
        options(joinedload(model.geometry))
    documents_query = add_load_for_profiles(documents_query, model)

    documents = documents_query.all()

    if lang is not None:
        set_best_locale(documents, lang)

    # make sure the documents stay in the same order as returned by ES
    document_index = {doc.document_id: doc for doc in documents}
    return [document_index[id] for id in document_ids if id in document_index]


def try_to_parse_document_id(search_term):
    try:
        return int(search_term)
    except ValueError:
        return None
