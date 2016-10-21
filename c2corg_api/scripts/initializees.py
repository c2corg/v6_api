import os
import sys

from c2corg_api.search.mappings.area_mapping import SearchArea
from c2corg_api.search.mappings.article_mapping import SearchArticle
from c2corg_api.search.mappings.book_mapping import SearchBook
from c2corg_api.search.mappings.image_mapping import SearchImage
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from elasticsearch_dsl import Index

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars

from c2corg_api.search.mapping import analysis_settings
from c2corg_api.search import configure_es_from_config, elasticsearch_config


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    configure_es_from_config(settings)
    setup_es()


def setup_es():
    """Create the ElasticSearch index and configure the mapping.
    """
    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']

    info = client.info()
    print('ElasticSearch version: {0}'.format(info['version']['number']))

    if client.indices.exists(index_name):
        print('Index "{0}" already exists. To re-create the index, manually '
              'delete the index and run this script again.'.format(index_name))
        print('To delete the index run:')
        print('curl -XDELETE \'http://{0}:{1}/{2}/\''.format(
            elasticsearch_config['host'], elasticsearch_config['port'],
            index_name))
        sys.exit(0)

    index = Index(index_name)
    index.settings(analysis=analysis_settings)

    index.doc_type(SearchArea)
    index.doc_type(SearchBook)
    index.doc_type(SearchImage)
    index.doc_type(SearchOuting)
    index.doc_type(SearchRoute)
    index.doc_type(SearchTopoMap)
    index.doc_type(SearchUser)
    index.doc_type(SearchWaypoint)
    index.doc_type(SearchArticle)

    index.create()

    print('Index "{0}" created'.format(index_name))


def drop_index(silent=True):
    """Remove the ElasticSearch index.
    """
    index = Index(elasticsearch_config['index'])
    try:
        index.delete()
    except Exception as exc:
        if not silent:
            raise exc
