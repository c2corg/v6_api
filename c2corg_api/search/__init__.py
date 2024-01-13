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
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl.query import MultiMatch

# the maximum number of documents that can be returned for each document type
SEARCH_LIMIT_MAX = 50

# the default limit value (how many documents are returned at once for each
# document type in a search request)
SEARCH_LIMIT_DEFAULT = 10

elasticsearch_config = {
    'client': None,
    'index': None,
    'host': None,
    'port': None
}


def client_from_config(settings):
    return Elasticsearch([{
        'host': settings['elasticsearch.host'],
        'port': int(settings['elasticsearch.port'])
    }], maxsize=int(settings['elasticsearch.pool']))


def configure_es_from_config(settings):
    global elasticsearch_config
    client = client_from_config(settings)
    connections.add_connection('default', client)
    elasticsearch_config['client'] = client
    elasticsearch_config['index'] = settings['elasticsearch.index']
    elasticsearch_config['host'] = settings['elasticsearch.host']
    elasticsearch_config['port'] = int(settings['elasticsearch.port'])


def create_search(document_type):
    return Search(
        using=elasticsearch_config['client'],
        index=elasticsearch_config['index'],
        doc_type=search_documents[document_type])


def get_text_query_on_title(search_term, search_lang=None):
    fields = []
    # search in all title* (title_en, title_fr, ...) fields.
    if not search_lang:
        fields.append('title_*.ngram')
        fields.append('title_*.raw^2')
    else:
        # if a language is given, boost the fields for the language
        for lang in default_langs:
            if lang == search_lang:
                fields.append('title_{0}.ngram^2'.format(lang))
                fields.append('title_{0}.raw^3'.format(lang))
            else:
                fields.append('title_{0}.ngram'.format(lang))
                fields.append('title_{0}.raw^2'.format(lang))

    return MultiMatch(
        query=search_term,
        fuzziness='auto',
        operator='and',
        fields=fields
    )


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
    WAYPOINT_TYPE: SearchWaypoint
}
