from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.search.mappings.area_mapping import SearchArea
from c2corg_api.search.mappings.image_mapping import SearchImage
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from elasticsearch import Elasticsearch
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch
from kombu.connection import Connection
from kombu import Exchange, Queue, pools

batch_size = 1000

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
    }])


def configure_es_from_config(settings):
    global elasticsearch_config
    client = client_from_config(settings)
    connections.add_connection('default', client)
    elasticsearch_config['client'] = client
    elasticsearch_config['index'] = settings['elasticsearch.index']
    elasticsearch_config['host'] = settings['elasticsearch.host']
    elasticsearch_config['port'] = int(settings['elasticsearch.port'])


def get_queue_config(settings):
    # set the number of connections to Redis
    pools.set_limit(int(settings['redis.queue_pool']))

    class QueueConfiguration(object):
        def __init__(self, settings):
            self.connection = Connection(settings['redis.url'])
            self.exchange = Exchange(settings['redis.exchange'], type='direct')
            self.queue = Queue(settings['redis.queue_es_sync'], self.exchange)

    return QueueConfiguration(settings)


def create_search(document_type):
    return Search(
        using=elasticsearch_config['client'],
        index=elasticsearch_config['index'],
        doc_type=search_documents[document_type])


def get_text_query(search_term):
    # search in all title* (title_en, title_fr, ...), summary* and
    # description* fields. "boost" title fields and summary fields.
    return MultiMatch(
        query=search_term,
        fields=['title*^3', 'summary*^2', 'description*']
    )

search_documents = {
    AREA_TYPE: SearchArea,
    IMAGE_TYPE: SearchImage,
    OUTING_TYPE: SearchOuting,
    ROUTE_TYPE: SearchRoute,
    MAP_TYPE: SearchTopoMap,
    USERPROFILE_TYPE: SearchUser,
    WAYPOINT_TYPE: SearchWaypoint
}
