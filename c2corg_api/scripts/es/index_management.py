"""Helpers to switch to a new ElasticSearch index without interrupting search.

The API always talks to `elasticsearch.index`. For a zero-downtime reindex that
name has to be an *alias* pointing to a timestamped index (`c2corg_2026...`).
A new index is built and filled while the alias still points to the old one,
then the alias is moved in one atomic operation.
"""

import logging
from datetime import UTC, datetime

from c2corg_api.search import search_documents
from c2corg_api.search.mapping import analysis_settings

log = logging.getLogger(__name__)

# what ES uses when nothing else is configured
DEFAULT_REFRESH_INTERVAL = '1s'
DEFAULT_REPLICAS = 1

ALIAS = 'alias'
CONCRETE_INDEX = 'index'
MISSING = 'missing'


def new_index_name(alias, now=None):
    now = now or datetime.now(UTC)
    return f'{alias}_{now:%Y%m%d%H%M%S}'


def get_target_state(client, name):
    """Tell what `name` currently is in the cluster.

    Returns a tuple `(state, indices)`:
    - `(ALIAS, [index, ...])` when it is an alias
    - `(CONCRETE_INDEX, [name])` when it is a real index (not yet migrated
      to the alias scheme)
    - `(MISSING, [])` when it does not exist
    """
    if client.indices.exists_alias(name=name):
        return ALIAS, sorted(client.indices.get_alias(name=name))
    if client.indices.exists(index=name):
        return CONCRETE_INDEX, [name]
    return MISSING, []


def get_serving_settings(client, indices):
    """Return the (refresh_interval, number_of_replicas) of the live index.

    The new index gets the same values once it is filled. Falls back to the
    ES defaults when there is no live index.
    """
    for index in indices:
        settings = client.indices.get_settings(index=index)[index]['settings']['index']
        return (
            settings.get('refresh_interval', DEFAULT_REFRESH_INTERVAL),
            int(settings.get('number_of_replicas', DEFAULT_REPLICAS)),
        )
    return DEFAULT_REFRESH_INTERVAL, DEFAULT_REPLICAS


def create_index(client, index_name, bulk_load=False):
    """Create an index with the analysis settings and the mapping of every type.

    With `bulk_load` the index is tuned for the initial import: no replicas
    and no periodic refresh. Call `finish_bulk_load` once it is filled.
    """
    settings = {'analysis': analysis_settings}
    if bulk_load:
        settings['refresh_interval'] = '-1'
        settings['number_of_replicas'] = 0

    client.indices.create(index=index_name, body={'settings': settings})

    # Apply the correct mapping for every document type (if we let ES infer
    # types, some fields could get a wrong one, e.g. geom -> double instead
    # of geo_point).
    for search_class in search_documents.values():
        search_class._doc_type.mapping.save(index_name)


def finish_bulk_load(client, index_name, refresh_interval, number_of_replicas):
    """Restore the normal settings of an index filled with `bulk_load`."""
    client.indices.put_settings(
        index=index_name,
        body={
            'index': {
                'refresh_interval': refresh_interval,
                'number_of_replicas': number_of_replicas,
            }
        },
    )
    client.indices.refresh(index=index_name)


def count_documents(client, index_name):
    client.indices.refresh(index=index_name)
    return client.count(index=index_name)['count']


def switch_alias(client, alias, new_index, state, old_indices):
    """Make `alias` point to `new_index`.

    When the alias already exists, the move is atomic. When `alias` is a real
    index (first run, before the migration to aliases) it has to be deleted
    first: ES does not allow to replace an index by an alias atomically, so
    the search has a short gap (two requests) in that single case.
    """
    if state == CONCRETE_INDEX:
        client.indices.delete(index=alias)
        client.indices.put_alias(index=new_index, name=alias)
        return

    actions = [{'remove': {'index': old, 'alias': alias}} for old in old_indices]
    actions.append({'add': {'index': new_index, 'alias': alias}})
    client.indices.update_aliases(body={'actions': actions})


def delete_indices(client, indices):
    for index in indices:
        log.info(f'Deleting index {index}')
        client.indices.delete(index=index)
