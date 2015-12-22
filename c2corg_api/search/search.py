from c2corg_api.views.document import set_best_locale
from elasticsearch_dsl.query import MultiMatch
from elasticsearch_dsl.filter import Term
from sqlalchemy.orm import joinedload

from c2corg_api.models import DBSession
from c2corg_api.search import create_search
from c2corg_api.views import to_json_dict


def search_for_type(
        search_term, document_type, model, schema, adapt_schema, limit, lang):
    # search in all title* (title_en, title_fr, ...), summary* and
    # description* fields. "boost" title fields and summary fields.
    search_query = MultiMatch(
        query=search_term,
        fields=['title*^3', 'summary*^2', 'description*']
    )

    # filter on the document_type
    type_query = Term(doc_type=document_type)

    search = create_search().\
        query(search_query).\
        filter(type_query).\
        fields([]).\
        extra(from_=0, size=limit)

    # only request the document ids from ES
    response = search.execute()
    document_ids = [int(doc.meta.id) for doc in response]

    # then load the documents for the returned ids
    documents = get_documents(document_ids, model, lang)

    count = len(documents)
    total = response.hits.total

    return {
        'count': count,
        'total': total,
        'documents': [
            to_json_dict(doc, adapt_schema(schema, doc)) for doc in documents
        ]
    }


def get_documents(document_ids, model, lang):
    """Load the documents for the given ids.
    The documents are returned in the same order as the ids. If a document
    for a given id does not exist, the document is skipped.
    """
    if not document_ids:
        return []

    documents = DBSession.\
        query(model).\
        filter(model.document_id.in_(document_ids)).\
        options(joinedload(model.locales)). \
        options(joinedload(model.geometry)). \
        all()

    if lang is not None:
        set_best_locale(documents, lang)

    # make sure the documents stay in the same order as returned by ES
    document_index = {doc.document_id: doc for doc in documents}
    return [document_index[id] for id in document_ids if id in document_index]
