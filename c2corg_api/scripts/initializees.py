import os
import sys

from c2corg_api.search.mappings.area_mapping import SearchArea, AREA_TYPE
from c2corg_api.search.mappings.article_mapping import SearchArticle, ARTICLE_TYPE
from c2corg_api.search.mappings.book_mapping import SearchBook, BOOK_TYPE
from c2corg_api.search.mappings.image_mapping import SearchImage, IMAGE_TYPE
from c2corg_api.search.mappings.outing_mapping import SearchOuting, OUTING_TYPE
from c2corg_api.search.mappings.xreport_mapping import SearchXreport, XREPORT_TYPE
from c2corg_api.search.mappings.route_mapping import SearchRoute, ROUTE_TYPE
from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap, MAP_TYPE
from c2corg_api.search.mappings.user_mapping import SearchUser, USERPROFILE_TYPE
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint, WAYPOINT_TYPE
from elasticsearch_dsl import Index

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars

from c2corg_api.search.mapping import es_index_settings
from c2corg_api.search import configure_es_from_config, elasticsearch_config

# TODO : use from c2corg_api.search import search_documents

_types = [
    (SearchArea, AREA_TYPE),
    (SearchArticle, ARTICLE_TYPE),
    (SearchBook, BOOK_TYPE),
    (SearchImage, IMAGE_TYPE),
    (SearchOuting, OUTING_TYPE),
    (SearchXreport, XREPORT_TYPE),
    (SearchRoute, ROUTE_TYPE),
    (SearchTopoMap, MAP_TYPE),
    (SearchUser, USERPROFILE_TYPE),
    (SearchWaypoint, WAYPOINT_TYPE),
]

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
    index_prefix = elasticsearch_config['index_prefix']

    info = client.info()
    print('ElasticSearch version: {0}'.format(info['version']['number']))

    for klass, letter in _types:
        index_name = f"{index_prefix}_{letter}"

        if client.indices.exists(index_name):
            print('Index "{0}" already exists. To re-create the index, manually '
                'delete the index and run this script again.'.format(index_name))
            print('To delete the index run:')
            print('curl -XDELETE \'http://{0}:{1}/{2}/\''.format(
                elasticsearch_config['host'], elasticsearch_config['port'],
                index_name))
            sys.exit(0)

        index = Index(index_name)
        index.settings(**es_index_settings)

        index.document(klass)
        index.create()
        print('Index "{0}" created'.format(index_name))

    # index = Index(index_name)
    # index.settings(**es_index_settings)

    # index.document(SearchArea)
    # index.document(SearchBook)
    # index.document(SearchImage)
    # index.document(SearchOuting)
    # index.document(SearchXreport)
    # index.document(SearchRoute)
    # index.document(SearchTopoMap)
    # index.document(SearchUser)
    # index.document(SearchWaypoint)
    # index.document(SearchArticle)

    # index.create()

    # print('Index "{0}" created'.format(index_name))


def drop_index(silent=True):
    """Remove the ElasticSearch index.
    """

    index_prefix = elasticsearch_config['index_prefix']

    for _, letter in _types:
        index = Index(f"{index_prefix}_{letter}")

        try:
            index.delete()
        except Exception as exc:
            if not silent:
                raise exc
