import sys

import os
from c2corg_api.search import configure_es_from_config, elasticsearch_config
from c2corg_api.search.mappings.route_mapping import SearchRoute
from elasticsearch_dsl import Index
from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )
from pyramid.scripts.common import parse_vars


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
    migrate()


def migrate():
    """ Add the field "slackline_type" to the route mapping.
    """
    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']
    mapping_name = SearchRoute._doc_type.name
    field_name = 'slackline_type'

    info = client.info()
    print('ElasticSearch version: {0}'.format(info['version']['number']))

    if not client.indices.exists(index_name):
        print('Index "{0}" does not exists!'.format(index_name))
        sys.exit(0)

    index = Index(index_name)
    field_mapping = index.connection.indices.get_field_mapping(
        index=index_name,
        doc_type=mapping_name,
        fields=field_name
        )

    if field_mapping:
        print('Field "{0}" already exists'.format(field_name))
        sys.exit(0)

    # see:
    # https://www.elastic.co/guide/en/elasticsearch/reference/2.3/indices-put-mapping.html
    index.connection.indices.put_mapping(
        index=index_name,
        doc_type=mapping_name,
        body={
            'properties': {
                field_name: SearchRoute.queryable_fields['sltyp'].to_dict()
            }
        }
    )

    print('Field "{0}" created'.format(field_name))


if __name__ == "__main__":
    main()
