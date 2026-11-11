"""Rebuild the whole ElasticSearch index without interrupting the search.

A new index (`<elasticsearch.index>_<timestamp>`) is created and filled while
the live one keeps serving requests (and keeps being updated by the syncer).
Once it contains every document, `<elasticsearch.index>` is moved to it
atomically and the old index is deleted.

Usage: reindex_es <config_uri> [--replace-index] [--keep-old] [var=value]

`elasticsearch.index` must be an alias for the zero-downtime switch. If it is
still a real index (first run), pass `--replace-index`: the old index is then
deleted just before the alias is created, which interrupts the search for a
very short time, once.
"""

import logging
import os
import sys

import transaction
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import sessionmaker
from zope.sqlalchemy import register

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.models import es_sync
from c2corg_api.scripts.es import index_management
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search import configure_es_from_config, elasticsearch_config

log = logging.getLogger(__name__)


def usage(argv):
    cmd = os.path.basename(argv[0])
    print(
        f'usage: {cmd} <config_uri> [--replace-index] [--keep-old] [var=value]\n'
        f'(example: "{cmd} production.ini")'
    )
    sys.exit(1)


def main(argv=sys.argv):
    flags = {arg for arg in argv[1:] if arg.startswith('--')}
    args = [argv[0]] + [arg for arg in argv[1:] if not arg.startswith('--')]
    if len(args) < 2 or not flags <= {'--replace-index', '--keep-old'}:
        usage(argv)

    config_uri = args[1]
    options = parse_vars(args[2:])
    setup_logging(config_uri)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    Session = sessionmaker()  # noqa
    register(Session)
    session = Session(bind=engine)
    configure_es_from_config(settings)

    batch_size = int(settings.get('elasticsearch.batch_size.fill_index', 1000))

    reindex(
        session,
        batch_size,
        replace_index='--replace-index' in flags,
        keep_old='--keep-old' in flags,
    )


def reindex(session, batch_size=1000, replace_index=False, keep_old=False):
    client = elasticsearch_config['client']
    alias = elasticsearch_config['index']

    state, old_indices = index_management.get_target_state(client, alias)
    if state == index_management.CONCRETE_INDEX and not replace_index:
        raise SystemExit(
            f'"{alias}" is a real index, not an alias. Run once with '
            '--replace-index to switch to aliases (the search is interrupted '
            'for a very short time during that run).'
        )

    refresh_interval, replicas = index_management.get_serving_settings(
        client, old_indices
    )
    new_index = index_management.new_index_name(alias)

    print(f'Creating index {new_index} (currently serving "{alias}": {old_indices})')
    index_management.create_index(client, new_index, bulk_load=True)

    try:
        with transaction.manager:
            result = fill_index(
                session, batch_size, index_name=new_index, mark_updated=False
            )

        index_management.finish_bulk_load(client, new_index, refresh_interval, replicas)

        # bulk errors are only logged by ElasticBatch: do not put an
        # incomplete index in service
        indexed = index_management.count_documents(client, new_index)
        if indexed != result.count:
            raise RuntimeError(
                f'{new_index} contains {indexed} documents, {result.count} were '
                'expected, not switching. Check the logs for bulk errors.'
            )

        client.cluster.health(index=new_index, wait_for_status='yellow', timeout='5m')
    except BaseException:
        print(f'Failed, deleting {new_index}. "{alias}" has not been touched.')
        index_management.delete_indices(client, [new_index])
        raise

    index_management.switch_alias(client, alias, new_index, state, old_indices)
    print(f'"{alias}" now points to {new_index}')

    # the syncer kept updating the old index (and moved the sync status
    # forward) during the import: go back to the time the import started so
    # that everything modified since is replayed on the new index
    with transaction.manager:
        es_sync.mark_as_updated(session, result.sync_date)

    if state == index_management.ALIAS and not keep_old:
        index_management.delete_indices(client, old_indices)


if __name__ == '__main__':
    main()
