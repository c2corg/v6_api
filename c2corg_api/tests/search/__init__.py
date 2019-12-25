from c2corg_api.scripts import initializees
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search import elasticsearch_config, search_documents


def reset_search_index(session):
    """Recreate index and fill index.
    """
    initializees.drop_index()
    initializees.setup_es()
    fill_index(session)
    force_search_index()


def force_search_index():
    """Force that the search index is updated.
    """
    indices = elasticsearch_config['client'].indices
    index_prefix = elasticsearch_config['index_prefix']
    for type_letter in search_documents:
        indices.refresh(f"{index_prefix}_{type_letter}")
