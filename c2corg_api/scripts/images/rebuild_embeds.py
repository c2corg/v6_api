"""Fill again the images embedded in the texts of the locales ([img=ID]).

The API keeps `guidebook.image_embeds` up to date when a locale is saved. This
script fills it from the current texts: once after the migration that creates
the table, and later to repair it (e.g. after a change of the markdown parser,
or of texts written by SQL). It can run while the API runs.
"""

import argparse
import logging
import sys
import time

from sqlalchemy import engine_from_config, or_, select, union
from sqlalchemy.orm import with_polymorphic
from sqlalchemy.sql.sqltypes import String

from c2corg_api.config import get_appsettings, setup_logging
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.image_embed import ImageEmbed
from c2corg_api.views.markdown import NOT_MARKDOWN_PROPERTY, update_image_embeds

log = logging.getLogger(__name__)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Fill again the images embedded in the texts of the locales.'
    )
    parser.add_argument('config_uri', help='the settings, e.g. production.ini')
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='the locales read and saved at once (one transaction each)',
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)
    settings = get_appsettings(args.config_uri)
    DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))

    start = time.monotonic()
    locales, embeds = rebuild_image_embeds(DBSession, args.batch_size)
    print(
        f'{locales} locales read, {embeds} embeds stored, '
        f'in {time.monotonic() - start:.0f} s'
    )


def rebuild_image_embeds(session, batch_size=1000):
    """Store the embeds of every locale; return (locales read, embeds stored)."""
    # The locales read: the ones whose texts have "[img=", and the ones that
    # have embeds stored (their texts may have lost them). Each batch is a
    # transaction, recomputed from the texts as they are then.
    ids = sorted(session.execute(_candidate_locale_ids()).scalars())
    log.info(f'{len(ids)} locales to read')
    locales = with_polymorphic(DocumentLocale, '*')
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        with commit_or_rollback(session):
            update_image_embeds(
                session.query(locales).filter(locales.id.in_(batch)).all()
            )
        session.expunge_all()
        log.info(f'{start + len(batch)} / {len(ids)} locales')
    embeds = session.query(ImageEmbed).count()
    return len(ids), embeds


def _candidate_locale_ids():
    """Select the ids of the locales that have or had embedded images."""
    base = DocumentLocale.__table__
    joined = base
    tables = set()
    conditions = []
    for mapper in DocumentLocale.__mapper__.self_and_descendants:
        table = mapper.local_table
        if table in tables:
            continue
        tables.add(table)
        if table is not base:
            joined = joined.outerjoin(table, table.c.id == base.c.id)
        # the texts cooked, as views.markdown.get_locale_image_ids reads them
        conditions += [
            column.like('%[img=%')
            for column in table.columns
            if isinstance(column.type, String)
            and column.key not in NOT_MARKDOWN_PROPERTY
            and column.key != 'type'
        ]
    with_tags = select(base.c.id).select_from(joined).where(or_(*conditions))
    stored = select(ImageEmbed.document_locale_id)
    return union(with_tags, stored)


if __name__ == '__main__':
    main()
