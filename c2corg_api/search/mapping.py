from elasticsearch_dsl import DocType, String, Integer


class SearchDocument(DocType):
    """The ElasticSearch mapping for documents.
    """
    id = Integer()
    doc_type = String(index='not_analyzed')

    # fr
    title_fr = String(analyzer='french')
    summary_fr = String(analyzer='french')
    description_fr = String(analyzer='french')

    # it
    title_it = String(analyzer='italian')
    summary_it = String(analyzer='italian')
    description_it = String(analyzer='italian')

    # de
    title_de = String(analyzer='german')
    summary_de = String(analyzer='german')
    description_de = String(analyzer='german')

    # en
    title_en = String(analyzer='english')
    summary_en = String(analyzer='english')
    description_en = String(analyzer='english')

    # es
    title_es = String(analyzer='spanish')
    summary_es = String(analyzer='spanish')
    description_es = String(analyzer='spanish')

    # ca
    title_ca = String(analyzer='catalan')
    summary_ca = String(analyzer='catalan')
    description_ca = String(analyzer='catalan')

    # eu
    title_eu = String(analyzer='basque')
    summary_eu = String(analyzer='basque')
    description_eu = String(analyzer='basque')
