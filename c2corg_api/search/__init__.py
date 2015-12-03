from elasticsearch import Elasticsearch
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Search

from c2corg_api.search.mapping import SearchDocument

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


def create_search():
    return Search(
        elasticsearch_config['client'],
        index=elasticsearch_config['index'],
        doc_type=SearchDocument)
