import json

from c2corg_api.models.document import Document
from c2corg_api.search.mapping_types import QEnumArray, QLong, \
    QEnumRange
from c2corg_common.attributes import default_langs
from c2corg_common.sortable_search_attributes import sortable_quality_types
from elasticsearch_dsl import Document as DocType, Text as String, \
    Long, GeoPoint


class BaseMeta:
    # disable the '_all' field, see
    # https://www.elastic.co/guide/en/elasticsearch/reference/2.4/mapping-all-field.html

    # no more used :
    # https://www.elastic.co/guide/en/elasticsearch/reference/6.0/mapping-all-field.html

    # all = MetaField(enabled=False)
    pass


# for the title fields a simpler analyzer is used.
# the configuration is based on the one by Photon:
# https://github.com/komoot/photon/blob/master/es/mappings.json
# https://github.com/komoot/photon/blob/master/es/index_settings.json
def default_title_field():
    return String(
        # index='not_analyzed',
        similarity='c2corgsimilarity',
        fields={
            'ngram': String(
                analyzer='index_ngram', search_analyzer='search_ngram'),
            'raw': String(
                analyzer='index_raw', search_analyzer='search_raw')})


class SearchDocument(DocType):
    """The base ElasticSearch mapping for documents. Each document type has
    its own specific mapping.

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
    class Meta(BaseMeta):
        pass

    id = Long()
    # doc_type = Enum()
    quality = QEnumRange(
        'qa', model_field=Document.quality, enum_mapper=sortable_quality_types)
    available_locales = QEnumArray('l', enum=default_langs)
    geom = GeoPoint()

    # array of area ids
    areas = QLong('a', is_id=True)

    # fr
    title_fr = default_title_field()
    summary_fr = String(
        analyzer='index_french', search_analyzer='search_french')
    description_fr = String(
        analyzer='index_french', search_analyzer='search_french')

    # it
    title_it = default_title_field()
    summary_it = String(
        analyzer='index_italian', search_analyzer='search_italian')
    description_it = String(
        analyzer='index_italian', search_analyzer='search_italian')

    # de
    title_de = default_title_field()
    summary_de = String(
        analyzer='index_german', search_analyzer='search_german')
    description_de = String(
        analyzer='index_german', search_analyzer='search_german')

    # en
    title_en = default_title_field()
    summary_en = String(
        analyzer='index_english', search_analyzer='search_english')
    description_en = String(
        analyzer='index_english', search_analyzer='search_english')

    # es
    title_es = default_title_field()
    summary_es = String(
        analyzer='index_spanish', search_analyzer='search_spanish')
    description_es = String(
        analyzer='index_spanish', search_analyzer='search_spanish')

    # ca
    title_ca = default_title_field()
    summary_ca = String(
        analyzer='index_catalan', search_analyzer='search_catalan')
    description_ca = String(
        analyzer='index_catalan', search_analyzer='search_catalan')

    # eu
    title_eu = default_title_field()
    summary_eu = String(
        analyzer='index_basque', search_analyzer='search_basque')
    description_eu = String(
        analyzer='index_basque', search_analyzer='search_basque')

    @staticmethod
    def to_search_document(document, index_prefix, include_areas=True):
        search_document = {
            '_index': f"{index_prefix}_{document.type}",
            '_id': document.document_id,
            # '_type': document.type,
            'id': document.document_id
        }

        if document.redirects_to:
            # remove merged documents from the index
            search_document['_op_type'] = 'delete'
        else:
            search_document['_op_type'] = 'index'
            search_document['doc_type'] = document.type

            available_locales = []
            for locale in document.locales:
                available_locales.append(locale.lang)
                search_document['title_' + locale.lang] = locale.title
                # FIXME currently the full-text search only searches the title,
                # so summary and description are not indexed
                # search_document['summary_' + locale.lang] = \
                #     strip_bbcodes(locale.summary)
                # search_document['description_' + locale.lang] = \
                #     strip_bbcodes(locale.description)
            search_document['available_locales'] = available_locales

            if document.quality:
                search_document['quality'] = \
                    sortable_quality_types[document.quality]

            if document.geometry:
                search_document['geom'] = SearchDocument.get_geometry(
                    document.geometry)

            areas = []
            if include_areas:
                for area in document._areas:
                    areas.append(area.document_id)
            search_document['areas'] = areas

        return search_document

    @staticmethod
    def get_geometry(geometry):
        if geometry.lon_lat:
            geojson = json.loads(geometry.lon_lat)
            return geojson['coordinates']
        else:
            return None

    @staticmethod
    def copy_fields(search_document, document, fields):
        for field in fields:
            search_document[field] = getattr(document, field)

    @staticmethod
    def copy_enum_range_fields(
            search_document, document, fields, search_model):
        search_fields = search_model._doc_type.mapping
        for field in fields:
            search_field = search_fields[field]
            enum_mapper = search_field._enum_mapper
            val = getattr(document, field)

            if val:
                if not isinstance(val, str):
                    search_document[field] = [enum_mapper[v] for v in val]
                else:
                    search_document[field] = enum_mapper[val]


"""To support partial-matching required for the autocomplete search, we
have to set up a n-gram filter for each language analyzer. See also:
https://www.elastic.co/guide/en/elasticsearch/guide/2.4/_index_time_search_as_you_type.html
The original definitions of the analyzers are taken from here:
https://www.elastic.co/guide/en/elasticsearch/reference/2.4/analysis-lang-analyzer.html
"""

es_index_settings = {
    "index": {
        "similarity": {
            "c2corgsimilarity": {
                "type": "BM25"
            }
        }
    },
    "analysis": {
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
                "articles_case": True,
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
                "articles_case": True,
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
                "articles_case": True,
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
        "char_filter": {
            "punctuationgreedy": {
                "type": "pattern_replace",
                "pattern": "[\\.,]"
            }
        },
        "analyzer": {
            "index_ngram": {
                "char_filter": ["punctuationgreedy"],
                "filter": [
                    "word_delimiter", "lowercase", "asciifolding", "unique",
                    "autocomplete_filter"],
                "tokenizer": "standard"
            },
            "search_ngram": {
                "char_filter": ["punctuationgreedy"],
                "filter": [
                    "word_delimiter", "lowercase", "asciifolding", "unique"],
                "tokenizer": "standard"
            },
            "index_raw": {
                "char_filter": ["punctuationgreedy"],
                "filter": [
                    "word_delimiter", "lowercase", "asciifolding", "unique"],
                "tokenizer": "standard"
            },
            "search_raw": {
                "char_filter": ["punctuationgreedy"],
                "filter": [
                    "word_delimiter", "lowercase", "asciifolding", "unique"],
                "tokenizer": "standard"
            },
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
}
