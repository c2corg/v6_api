import os
import sys

from elasticsearch_dsl import Index

from c2corg_api.config import (
    get_appsettings,
    parse_vars,
    setup_logging,
)
from c2corg_api.search import configure_es_from_config, elasticsearch_config
from c2corg_api.search.mappings.route_mapping import SearchRoute


def usage(argv):
    cmd = os.path.basename(argv[0])
    print(f'usage: {cmd} <config_uri> [var=value]\n(example: "{cmd} development.ini")')
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
    """Add the field "slackline_type" to the route mapping."""
    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']
    mapping_name = SearchRoute._doc_type.name
    field_name = 'slackline_type'

    info = client.info()
    print('ElasticSearch version: {}'.format(info['version']['number']))

    if not client.indices.exists(index_name):
        print(f'Index "{index_name}" does not exists!')
        sys.exit(0)

    index = Index(index_name)
    field_mapping = index.connection.indices.get_field_mapping(
        index=index_name, doc_type=mapping_name, fields=field_name
    )

    if field_mapping:
        print(f'Field "{field_name}" already exists')
        sys.exit(0)

    # see:
    # https://www.elastic.co/guide/en/elasticsearch/reference/2.3/indices-put-mapping.html
    index.connection.indices.put_mapping(
        index=index_name,
        doc_type=mapping_name,
        body={
            'properties': {field_name: SearchRoute.queryable_fields['sltyp'].to_dict()}
        },
    )

    print(f'Field "{field_name}" created')


if __name__ == '__main__':
    main()
