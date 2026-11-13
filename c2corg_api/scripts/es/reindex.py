"""Rebuild the whole ElasticSearch index without interrupting the search.

There is one index per document type, named `<elasticsearch.index>_<type>`. New
indices (`<elasticsearch.index>_<type>_<timestamp>`) are created and filled
while the live ones keep serving requests (and keep being updated by the
syncer). Once they contain every document, the names of the document types are
moved to them atomically (they are aliases) and the old indices are deleted.

Usage: reindex_es <config_uri> [--replace-index] [--keep-old] [var=value]

The names of the document types must be aliases for the zero-downtime switch. If
they are still real indices (first run), pass `--replace-index`: the old indices
are then deleted just before the aliases are created, which interrupts the
search for a very short time, once.
"""

import logging
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import sessionmaker

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.models import commit_or_rollback, es_sync
from c2corg_api.scripts.es import index_management
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search import (
    configure_es_from_config,
    elasticsearch_config,
    index_name,
    search_documents,
)

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

    # per document type: the alias served to the API, and what it is now
    targets = {}
    for doc_type in search_documents:
        alias = index_name(doc_type)
        targets[doc_type] = (alias, *index_management.get_target_state(client, alias))

    concrete = [
        alias
        for alias, state, _ in targets.values()
        if state == index_management.CONCRETE_INDEX
    ]
    if concrete and not replace_index:
        raise SystemExit(
            f'{", ".join(concrete)}: real indices, not aliases. Run once with '
            '--replace-index to switch to aliases (the search of these document '
            'types is interrupted for a very short time during that run).'
        )

    all_old = [index for _, _, old in targets.values() for index in old]
    refresh_interval, replicas = index_management.get_serving_settings(client, all_old)

    new_indices = {
        doc_type: index_management.new_index_name(alias)
        for doc_type, (alias, _, _) in targets.items()
    }

    try:
        for doc_type, new_index in new_indices.items():
            alias, _, old_indices = targets[doc_type]
            print(f'Creating {new_index} (serving "{alias}": {old_indices})')
            index_management.create_index(client, new_index, doc_type, bulk_load=True)

        with commit_or_rollback(session):
            result = fill_index(
                session, batch_size, index_names=new_indices, mark_updated=False
            )

        for new_index in new_indices.values():
            index_management.finish_bulk_load(
                client, new_index, refresh_interval, replicas
            )

        # bulk errors are only logged by ElasticBatch: do not put an
        # incomplete index in service
        for doc_type, new_index in new_indices.items():
            indexed = index_management.count_documents(client, new_index)
            expected = result.counts[doc_type]
            if indexed != expected:
                raise RuntimeError(
                    f'{new_index} contains {indexed} documents, {expected} were '
                    'expected, not switching. Check the logs for bulk errors.'
                )

        client.cluster.health(
            index=','.join(new_indices.values()), wait_for_status='yellow', timeout='5m'
        )
    except BaseException:
        print(
            'Failed, deleting the new indices. The served ones have not been touched.'
        )
        index_management.delete_indices(client, list(new_indices.values()))
        raise

    index_management.switch_aliases(
        client,
        [
            (alias, new_indices[doc_type], state, old_indices)
            for doc_type, (alias, state, old_indices) in targets.items()
        ],
    )
    print('The aliases now point to: ' + ', '.join(new_indices.values()))

    # the syncer kept updating the old indices (and moved the sync status
    # forward) during the import: go back to the time the import started so
    # that everything modified since is replayed on the new indices
    with commit_or_rollback(session):
        es_sync.mark_as_updated(session, result.sync_date)

    if not keep_old:
        index_management.delete_indices(
            client,
            [
                index
                for _, state, old_indices in targets.values()
                if state == index_management.ALIAS
                for index in old_indices
            ],
        )


if __name__ == '__main__':
    main()
