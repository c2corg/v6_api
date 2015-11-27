from c2corg_api.search import elasticsearch_config


def force_search_index():
    """Force that the search index is updated.
    """
    elasticsearch_config['client'].indices.refresh(
        elasticsearch_config['index'])
