import os
import sys
import pycurl
from io import BytesIO

# from c2corg_api.search.mappings.area_mapping import SearchArea
# from c2corg_api.search.mappings.article_mapping import SearchArticle
# from c2corg_api.search.mappings.book_mapping import SearchBook
# from c2corg_api.search.mappings.image_mapping import SearchImage
# from c2corg_api.search.mappings.outing_mapping import SearchOuting
# from c2corg_api.search.mappings.xreport_mapping import SearchXreport
# from c2corg_api.search.mappings.route_mapping import SearchRoute
# from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap
# from c2corg_api.search.mappings.user_mapping import SearchUser
# from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint

from elasticsearch_dsl import Index

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars

# from c2corg_api.search.mapping import analysis_settings
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
    index_suffix_list = ["_a", "_b", "_c", "_i",
                         "_m", "_o", "_r", "_u", "_w", "_x"]

    client = elasticsearch_config['client']
    index_name = elasticsearch_config['index']
    cible = elasticsearch_config['host']+':'+str(elasticsearch_config['port'])
    print('cible es: %s', cible)

    info = client.info()
    print('ElasticSearch version: {0}'.format(info['version']['number']))

    for index_suffix in index_suffix_list:
        print("suffix : ", index_suffix)
        if client.indices.exists(index_name[:-2]+index_suffix):
            print('Index "{0}" already exists. deleting it {0}... '
                  .format(index_name[:-2]+index_suffix))
            """ print('To delete the index run:')
            print('curl -XDELETE \'http://{0}:{1}/{2}/\''.format(
               elasticsearch_config['host'], elasticsearch_config['port'],
               index_name+index_suffix)) """
            delete_indice(cible, index_name[:-2]+index_suffix)

    for index_suffix in index_suffix_list:
        print('Index "{0}" to create'.format(index_name[:-2]+index_suffix))
        create_indice(cible, index_name[:-2]+index_suffix)
        print('Index "{0}" created'.format(index_name[:-2]+index_suffix))
        indice_settings_update(cible, index_name[:-2]+index_suffix)
        print('Index "{0}" settings'.format(index_name[:-2] + index_suffix))
        indice_mapping_update(cible,
                              index_name[:-2]+index_suffix, index_suffix[1])
        print('Index "{0}" mappings'.format(index_name[:-2] + index_suffix))

    print('all indexes are created')


def drop_index(silent=True):
    """Remove the ElasticSearch index.
    """
    index = Index(elasticsearch_config['index'])
    try:
        index.delete()
    except Exception as exc:
        if not silent:
            raise exc


def delete_indice(cible, indice_name):
    buffer = BytesIO()
    c = pycurl.Curl()
    header = ['Content-Type: application/json']
    c.setopt(c.HTTPHEADER, header)
    c.setopt(c.CUSTOMREQUEST, 'DELETE')
    c.setopt(c.URL, 'http://' + cible + '/' + indice_name)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    c.close()

    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))


def create_indice(cible, indice_name):
    buffer = BytesIO()
    c = pycurl.Curl()
    header = ['Content-Type: application/json']
    c.setopt(c.HTTPHEADER, header)
    c.setopt(c.CUSTOMREQUEST, 'PUT')
    c.setopt(c.URL, 'http://' + cible + '/' + indice_name)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    c.close()

    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))


def indice_settings_update(cible, indice_name):
    buffer = BytesIO()
    c = pycurl.Curl()
    header = ['Content-Type: application/json']
    c.setopt(c.HTTPHEADER, header)
    c.setopt(c.CUSTOMREQUEST, 'POST')
    c.setopt(c.URL, 'http://' + cible + '/' + indice_name + '/_close')
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))

    file = "./scripts/esjson5-6/settings.json"
    f = open(file)
    post_data = f.read()
    c.setopt(c.CUSTOMREQUEST, 'PUT')
    c.setopt(c.URL, 'http://' + cible + '/' + indice_name + '/_settings')
    c.setopt(c.POSTFIELDS, post_data)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))

    c.setopt(c.HTTPHEADER, header)
    c.setopt(c.CUSTOMREQUEST, 'POST')
    c.setopt(c.URL, 'http://' + cible + '/' + indice_name + '/_open')
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))

    c.close()


def indice_mapping_update(cible, indice_name, mapping_type):
    file = "./scripts/esjson5-6/"+mapping_type+".json"
    f = open(file)
    post_data = f.read()

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, 'http://'+cible+'/'+indice_name+'/_mapping/_doc')
    header = ['Content-Type: application/json']
    c.setopt(c.HTTPHEADER, header)
    c.setopt(c.CUSTOMREQUEST, 'PUT')
    c.setopt(c.POSTFIELDS, post_data)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    c.close()

    body = buffer.getvalue()
    print(body.decode('iso-8859-1'))
