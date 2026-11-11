import re

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl.query import Bool, MultiMatch
from kombu import Exchange, Queue, pools
from kombu.connection import Connection

from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.search.mappings.area_mapping import SearchArea
from c2corg_api.search.mappings.article_mapping import SearchArticle
from c2corg_api.search.mappings.book_mapping import SearchBook
from c2corg_api.search.mappings.image_mapping import SearchImage
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.mappings.xreport_mapping import SearchXreport

# the maximum number of documents that can be returned for each document type
SEARCH_LIMIT_MAX = 50

# the default limit value (how many documents are returned at once for each
# document type in a search request)
SEARCH_LIMIT_DEFAULT = 10

elasticsearch_config = {'client': None, 'index': None, 'host': None, 'port': None}


def client_from_config(settings):
    return Elasticsearch(
        [
            {
                'host': settings['elasticsearch.host'],
                'port': int(settings['elasticsearch.port']),
            }
        ],
        maxsize=int(settings['elasticsearch.pool']),
    )


def configure_es_from_config(settings):
    client = client_from_config(settings)
    connections.add_connection('default', client)
    elasticsearch_config['client'] = client
    elasticsearch_config['index'] = settings['elasticsearch.index']
    elasticsearch_config['host'] = settings['elasticsearch.host']
    elasticsearch_config['port'] = int(settings['elasticsearch.port'])


def get_queue_config(settings):
    # set the number of connections to Redis
    pools.set_limit(int(settings['redis.queue_pool']))

    class QueueConfiguration:
        def __init__(self, settings):
            self.connection = Connection(
                settings['redis.url'], virtual_host=settings['redis.db_queue']
            )
            self.exchange = Exchange(settings['redis.exchange'], type='direct')
            self.queue = Queue(settings['redis.queue_es_sync'], self.exchange)

    return QueueConfiguration(settings)


def create_search(document_type):
    return Search(
        using=elasticsearch_config['client'],
        index=elasticsearch_config['index'],
        doc_type=search_documents[document_type],
    )


# any run of non-word characters (space, hyphen, colon, apostrophe, slash,
# ...) separates two "words", the same way the ES tokenizers used on the
# title fields would split them. This is what decides whether a search term
# like "Mont-Blanc" is treated as one word (typo-tolerant prefix search) or
# several (word-order-independent search) - counting literal spaces only
# would miss separators such as hyphens and treat "Mont-Blanc" as a single
# word.
_WORD_RE = re.compile(r'\w+', re.UNICODE)


# Relative weights of the clauses of the title query. They only need to keep
# this order: whole word > stemmed word > phrase bonus > prefix > typo.
_BOOST_EXACT = 10
_BOOST_STEMMED = 3
_BOOST_PHRASE = 2
_BOOST_PREFIX = 1
_BOOST_FUZZY = 0.2

# below this length a fuzzy match is too loose (every 4-letter word is one
# edit away from dozens of others)
_FUZZY_MIN_LENGTH = 5


def _title_fields(suffix, search_lang):
    """Return the `title_<lang>.<suffix>` field of every language.

    Always search every language, using explicit field names rather than a
    `title_*` wildcard so the query does not depend on ES resolving the
    field pattern correctly. Documents only translated in a language other
    than the preferred one (e.g. waypoints) must still be found. The
    preferred language (if given) is boosted so its matches rank first
    without excluding the other languages.
    """
    return [
        f'title_{lang}.{suffix}' + ('^3' if search_lang and lang == search_lang else '')
        for lang in default_langs
    ]


def get_text_query_on_title(search_term, search_lang=None):
    """Build the text query used on the titles of the documents.

    The same query is used whatever the number of words (it used to be a
    typo-tolerant prefix query for one word and a stemmed exact query for
    several, which gave contradictory results: "Vens" ranked far behind
    unrelated titles, but "le Vens" found it first). It is a disjunction of
    clauses of decreasing strictness, so the better the match, the higher
    the score:

    - `raw`: all the words, as written (only case and accents ignored).
      Without this clause a whole word could not be told apart from the
      beginning of a longer one, since the `ngram` fields index prefixes.
    - `contentheavy`: all the words, in any order, stemmed and without stop
      words ("Arêtes de Gerbier" matches "Gerbier : Traversée des arêtes"),
      plus a bonus when they also appear close to each other.
    - `ngram`: the last word may be incomplete (as-you-type), the other
      ones must be complete words.
    - a typo-tolerant match on the `ngram` fields, for long single words
      only. It is not applied to several words: once stemmed, distinct
      short words can be one edit apart and unrelated titles would match.
    """
    words = _WORD_RE.findall(search_term)
    stemmed_fields = _title_fields('contentheavy', search_lang)
    ngram_fields = _title_fields('ngram', search_lang)

    should = [
        MultiMatch(
            query=search_term,
            fields=_title_fields('raw', search_lang),
            type='best_fields',
            operator='and',
            zero_terms_query='none',
            boost=_BOOST_EXACT,
        ),
        MultiMatch(
            query=search_term,
            fields=stemmed_fields,
            type='best_fields',
            operator='and',
            zero_terms_query='none',
            boost=_BOOST_STEMMED,
        ),
    ]

    if len(words) > 1:
        should.append(
            MultiMatch(
                query=search_term,
                fields=stemmed_fields,
                type='phrase',
                slop=4,
                zero_terms_query='none',
                boost=_BOOST_PHRASE,
            )
        )
        # the words but the last one must be complete. A word that is a stop
        # word in some language is ignored there (zero_terms_query='all'),
        # so "le vens" behaves like "vens".
        should.append(
            Bool(
                must=[
                    MultiMatch(
                        query=' '.join(words[:-1]),
                        fields=stemmed_fields,
                        type='best_fields',
                        operator='and',
                        zero_terms_query='all',
                    ),
                    MultiMatch(
                        query=words[-1],
                        fields=ngram_fields,
                        type='best_fields',
                        zero_terms_query='none',
                    ),
                ],
                boost=_BOOST_PREFIX,
            )
        )
    else:
        should.append(
            MultiMatch(
                query=search_term,
                fields=ngram_fields,
                type='best_fields',
                zero_terms_query='none',
                boost=_BOOST_PREFIX,
            )
        )
        if len(words[0] if words else '') >= _FUZZY_MIN_LENGTH:
            should.append(
                MultiMatch(
                    query=search_term,
                    fields=ngram_fields,
                    type='best_fields',
                    fuzziness=1,
                    # the first letter is assumed to be right: far fewer
                    # candidate terms, and typos rarely hit the first letter
                    prefix_length=1,
                    # max_expansions caps how many candidate terms the fuzzy
                    # match can consider, not the edit distance. With a low
                    # value the exact term the user typed can lose out to
                    # unrelated ones on an index as large as ours. 50 is
                    # elasticsearch's own default for fuzzy queries.
                    max_expansions=50,
                    zero_terms_query='none',
                    boost=_BOOST_FUZZY,
                )
            )

    return Bool(should=should, minimum_should_match=1)


search_documents = {
    AREA_TYPE: SearchArea,
    ARTICLE_TYPE: SearchArticle,
    BOOK_TYPE: SearchBook,
    IMAGE_TYPE: SearchImage,
    OUTING_TYPE: SearchOuting,
    XREPORT_TYPE: SearchXreport,
    ROUTE_TYPE: SearchRoute,
    MAP_TYPE: SearchTopoMap,
    USERPROFILE_TYPE: SearchUser,
    WAYPOINT_TYPE: SearchWaypoint,
}
