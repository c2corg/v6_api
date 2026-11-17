"""Compute again the quality of the outings already saved, with the rules of the UI.

See `README.md` next to this file, and `quality_rules.py` for the rules.
"""

import argparse
import logging
import sys
from collections import Counter

from sqlalchemy import engine_from_config, func
from sqlalchemy.orm import selectinload

from c2corg_api.config import get_appsettings, setup_logging
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.user import User
from c2corg_api.scripts.outings.quality_rules import OutingData, recomputed_quality
from c2corg_api.search import get_queue_config
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document import update_version

log = logging.getLogger(__name__)

DEFAULT_COMMENT = 'Quality computed again with the rules of November 2026'


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Compute again the quality of the outings, with the rules of '
        'the UI. A quality chosen by the author is kept.'
    )
    parser.add_argument('config_uri', help='the settings, e.g. production.ini')
    parser.add_argument(
        '--user-id',
        type=int,
        help='the user the new versions are saved by (required unless --dry-run)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='only count the outings that would change, change nothing',
    )
    parser.add_argument(
        '--comment', default=DEFAULT_COMMENT, help='the comment of the new versions'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='the outings read and saved at once (one transaction each)',
    )
    parser.add_argument(
        '--ids', type=int, nargs='+', help='only these outings (to try it first)'
    )
    args = parser.parse_args(argv[1:])
    if not args.dry_run and not args.user_id:
        parser.error('--user-id is required, unless --dry-run')
    return args


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)
    settings = get_appsettings(args.config_uri)
    DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))

    if not args.dry_run and not DBSession.get(User, args.user_id):
        sys.exit(f'ERROR: no user {args.user_id}')

    changes = recompute_quality(
        DBSession,
        user_id=None if args.dry_run else args.user_id,
        comment=args.comment,
        queue_config=None if args.dry_run else get_queue_config(settings),
        batch_size=args.batch_size,
        ids=args.ids,
    )

    verb = 'would change' if args.dry_run else 'changed'
    print(f'{sum(changes.values())} outings {verb}:')
    for (before, after), count in sorted(changes.items()):
        print(f'  {before} -> {after}: {count}')


def recompute_quality(
    session, user_id, comment, queue_config, batch_size=500, ids=None
):
    """Save the outings whose quality changes with the latest rules.

    Without `user_id`, nothing is saved (a dry run). Each batch of outings is
    a transaction: an interruption keeps the batches already saved, and a new
    run goes on (the outings already changed do not change again). Return the
    number of outings per change: `{('empty', 'draft'): 12, ...}`.
    """
    changes = Counter()
    for batch_ids in _batches(session, batch_size, ids):
        with commit_or_rollback(session):
            batch_changes = _recompute_batch(session, batch_ids, user_id, comment)
            if batch_changes and user_id and queue_config:
                notify_es_syncer(queue_config)
        changes.update(batch_changes)
        log.info(f'{len(batch_ids)} outings read, {sum(changes.values())} changes')
    return changes


def _batches(session, batch_size, ids):
    """Yield the ids of the outings, by batch, in the order of their ids."""
    query = session.query(Outing.document_id).filter(Outing.redirects_to.is_(None))
    if ids:
        query = query.filter(Outing.document_id.in_(ids))
    last_id = 0
    while True:
        batch = [
            row.document_id
            for row in query.filter(Outing.document_id > last_id)
            .order_by(Outing.document_id)
            .limit(batch_size)
        ]
        if not batch:
            return
        yield batch
        last_id = batch[-1]


def _recompute_batch(session, outing_ids, user_id, comment):
    outings = (
        session.query(Outing)
        .options(selectinload(Outing.locales))
        .filter(Outing.document_id.in_(outing_ids))
        .all()
    )
    with_track = _with_track(session, outing_ids)
    image_counts = _image_counts(session, outing_ids)

    changes = Counter()
    for outing in outings:
        has_track = outing.document_id in with_track
        image_count = image_counts.get(outing.document_id, 0)
        quality = recomputed_quality(
            outing.quality,
            [
                OutingData(outing, locale, has_track, image_count)
                for locale in outing.locales
            ],
        )
        if quality is None:
            continue

        changes[outing.quality, quality] += 1
        if user_id is None:
            continue

        outing.quality = quality
        update_version(outing, user_id, comment, [UpdateType.FIGURES], [])
        # the outing and the documents listing it (its routes, its users...)
        update_cache_version(outing)
    return changes


def _with_track(session, outing_ids):
    """Return the ids of the outings with a track, without loading the tracks."""
    return {
        row.document_id
        for row in session.query(DocumentGeometry.document_id).filter(
            DocumentGeometry.document_id.in_(outing_ids),
            DocumentGeometry.geom_detail.is_not(None),
        )
    }


def _image_counts(session, outing_ids):
    """Return the number of images of each outing (as the UI gets them)."""
    rows = (
        session.query(Association.parent_document_id, func.count())
        .join(Image, Image.document_id == Association.child_document_id)
        .filter(
            Association.parent_document_id.in_(outing_ids),
            Association.child_document_type == IMAGE_TYPE,
            Image.redirects_to.is_(None),
        )
        .group_by(Association.parent_document_id)
    )
    return dict(rows.all())


if __name__ == '__main__':
    main()
