from elasticsearch_dsl import DocType, String, Integer, MetaField


class SearchDocument(DocType):
    """The ElasticSearch mapping for documents.

    We are using the "one language per field" strategy, for example for the
    title field we have a field for each language: title_en, title_fr, ...
    See also:
    https://www.elastic.co/guide/en/elasticsearch/guide/current/one-lang-fields.html

    For the search a different analyzer is used than for the indexing. This is
    because the index analyzer uses n-grams, while the search words should
    not be cut into n-gram tokens.
    See also:
    https://www.elastic.co/guide/en/elasticsearch/guide/current/_index_time_search_as_you_type.html
    """
    id = Integer()
    doc_type = String(index='not_analyzed')

    # fr
    title_fr = String(
        analyzer='index_french', search_analyzer='search_french')
    summary_fr = String(
        analyzer='index_french', search_analyzer='search_french')
    description_fr = String(
        analyzer='index_french', search_analyzer='search_french')

    # it
    title_it = String(
        analyzer='index_italian', search_analyzer='search_italian')
    summary_it = String(
        analyzer='index_italian', search_analyzer='search_italian')
    description_it = String(
        analyzer='index_italian', search_analyzer='search_italian')

    # de
    title_de = String(
        analyzer='index_german', search_analyzer='search_german')
    summary_de = String(
        analyzer='index_german', search_analyzer='search_german')
    description_de = String(
        analyzer='index_german', search_analyzer='search_german')

    # en
    title_en = String(
        analyzer='index_english', search_analyzer='search_english')
    summary_en = String(
        analyzer='index_english', search_analyzer='search_english')
    description_en = String(
        analyzer='index_english', search_analyzer='search_english')

    # es
    title_es = String(
        analyzer='index_spanish', search_analyzer='search_spanish')
    summary_es = String(
        analyzer='index_spanish', search_analyzer='search_spanish')
    description_es = String(
        analyzer='index_spanish', search_analyzer='search_spanish')

    # ca
    title_ca = String(
        analyzer='index_catalan', search_analyzer='search_catalan')
    summary_ca = String(
        analyzer='index_catalan', search_analyzer='search_catalan')
    description_ca = String(
        analyzer='index_catalan', search_analyzer='search_catalan')

    # eu
    title_eu = String(
        analyzer='index_basque', search_analyzer='search_basque')
    summary_eu = String(
        analyzer='index_basque', search_analyzer='search_basque')
    description_eu = String(
        analyzer='index_basque', search_analyzer='search_basque')

    class Meta:
        # disable the '_all' field, see
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-all-field.html
        all = MetaField(enabled=False)

"""To support partial-matching required for the autocomplete search, we
have to set up a n-gram filter for each language analyzer. See also:
https://www.elastic.co/guide/en/elasticsearch/guide/current/_index_time_search_as_you_type.html
"""
analysis_settings = {
    "filter": {
        "autocomplete_filter": {
            "type": "edge_ngram",
            "min_gram": 2,
            "max_gram": 20
        },
        # filters for the english analyzers
        "english_stop": {
            "type": "stop",
            "stopwords": "_english_"
        },
        "english_stemmer": {
            "type": "stemmer",
            "language": "english"
        },
        "english_possessive_stemmer": {
            "type": "stemmer",
            "language": "possessive_english"
        },
        # filters for the french analyzers
        "french_elision": {
            "type": "elision",
            "articles": [
                "l", "m", "t", "qu", "n", "s",
                "j", "d", "c", "jusqu", "quoiqu",
                "lorsqu", "puisqu"
            ]
        },
        "french_stop": {
            "type": "stop",
            "stopwords": "_french_"
        },
        "french_stemmer": {
            "type": "stemmer",
            "language": "light_french"
        },
        # filters for the german analyzers
        "german_stop": {
            "type": "stop",
            "stopwords": "_german_"
        },
        "german_stemmer": {
            "type": "stemmer",
            "language": "light_german"
        },
        # filters for the italian analyzers
        "italian_elision": {
            "type": "elision",
            "articles": [
                "c", "l", "all", "dall", "dell",
                "nell", "sull", "coll", "pell",
                "gl", "agl", "dagl", "degl", "negl",
                "sugl", "un", "m", "t", "s", "v", "d"
            ]
        },
        "italian_stop": {
            "type": "stop",
            "stopwords": "_italian_"
        },
        "italian_stemmer": {
            "type": "stemmer",
            "language": "light_italian"
        },
        # filters for the spanish analyzers
        "spanish_stop": {
            "type": "stop",
            "stopwords": "_spanish_"
        },
        "spanish_stemmer": {
            "type": "stemmer",
            "language": "light_spanish"
        },
        # filters for the catalan analyzers
        "catalan_elision": {
            "type": "elision",
            "articles": ["d", "l", "m", "n", "s", "t"]
        },
        "catalan_stop": {
            "type": "stop",
            "stopwords": "_catalan_"
        },
        "catalan_stemmer": {
            "type": "stemmer",
            "language": "catalan"
        },
        # filters for the basque analyzers
        "basque_stop": {
            "type": "stop",
            "stopwords": "_basque_"
        },
        "basque_stemmer": {
            "type": "stemmer",
            "language": "basque"
        }
    },
    "analyzer": {
        "index_english": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": [
                "english_possessive_stemmer",
                "lowercase",
                "english_stop",
                "english_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_english": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": [
                "english_possessive_stemmer",
                "lowercase",
                "english_stop",
                "english_stemmer"
            ]
        },
        "index_french": {
            "tokenizer": "standard",
            "filter": [
                "french_elision",
                "lowercase",
                "french_stop",
                "french_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_french": {
            "tokenizer": "standard",
            "filter": [
                "french_elision",
                "lowercase",
                "french_stop",
                "french_stemmer",
                "autocomplete_filter"
            ]
        },
        "index_german": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "german_stop",
                "german_normalization",
                "german_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_german": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "german_stop",
                "german_normalization",
                "german_stemmer"
            ]
        },
        "index_italian": {
            "tokenizer": "standard",
            "filter": [
                "italian_elision",
                "lowercase",
                "italian_stop",
                "italian_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_italian": {
            "tokenizer": "standard",
            "filter": [
                "italian_elision",
                "lowercase",
                "italian_stop",
                "italian_stemmer"
            ]
        },
        "index_spanish": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "spanish_stop",
                "spanish_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_spanish": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "spanish_stop",
                "spanish_stemmer"
            ]
        },
        "index_catalan": {
            "tokenizer": "standard",
            "filter": [
                "catalan_elision",
                "lowercase",
                "catalan_stop",
                "catalan_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_catalan": {
            "tokenizer": "standard",
            "filter": [
                "catalan_elision",
                "lowercase",
                "catalan_stop",
                "catalan_stemmer"
            ]
        },
        "index_basque": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "basque_stop",
                "basque_stemmer",
                "autocomplete_filter"
            ]
        },
        "search_basque": {
            "tokenizer": "standard",
            "filter": [
                "lowercase",
                "basque_stop",
                "basque_stemmer"
            ]
        }
    }
}
