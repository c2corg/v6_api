"""TEMPORARY: backfill the older partner outings by hand (make backfill-partners).

Delete with the other `backfill_*` files (c2corg/v6_api#2763). See
`c2corg_api/jobs/backfill_partner_outings.py`.
"""

import argparse
import datetime
import logging
import sys

from sqlalchemy import engine_from_config
from sqlalchemy.orm import Session

from c2corg_api.config import get_appsettings, parse_vars, setup_logging
from c2corg_api.jobs import backfill_partner_outings as backfill
from c2corg_api.models import DBSession

log = logging.getLogger('c2corg_api_backfill_partners')


def _parser():
    parser = argparse.ArgumentParser(
        prog='backfill_partners.py',
        description='Backfill the older outings of the partner sites, a step at '
        'a time; each step resumes where the last one stopped.',
    )
    parser.add_argument('config_uri', help='development.ini, production.ini...')
    parser.add_argument(
        '--sources',
        help='comma separated, or "all" (default: $PARTNERS_BACKFILL_SOURCES)',
    )
    parser.add_argument(
        '--floor',
        type=datetime.date.fromisoformat,
        help='oldest outing date (default: $PARTNERS_BACKFILL_FLOOR, else the '
        f'start of the season {backfill.DEFAULT_SEASONS} seasons ago)',
    )
    parser.add_argument(
        '--steps', type=int, default=1, help='steps per source (default: 1)'
    )
    parser.add_argument('--pages', type=int, help='listing pages per step')
    parser.add_argument(
        '--details', type=int, help='detail pages, routes or summits per step'
    )
    parser.add_argument('--reset', action='store_true', help='start these sources over')
    parser.add_argument(
        '--status', action='store_true', help='print the progress and exit'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='also the sources switched off for the harvest',
    )
    return parser


def _print_states(session):
    rows = backfill.states(session)
    if not rows:
        print('no backfill yet')
    for name, row in rows.items():
        print(
            f'{name}: {row.last_status or "-"} cursor={row.cursor} '
            f'floor={row.floor} steps={row.steps} requests={row.requests} '
            f'upserted={row.upserted} finished={row.finished_at} '
            f'last={row.last_run_at} {row.last_detail or ""}'
        )


def main(argv=sys.argv):
    args, rest = _parser().parse_known_args(argv[1:])
    setup_logging(args.config_uri)
    settings = get_appsettings(args.config_uri, options=parse_vars(rest))
    DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))

    if args.status:
        with Session(DBSession.get_bind()) as session:
            _print_states(session)
        return 0
    requested = args.sources.split(',') if args.sources else None
    try:
        sources = backfill.backfill_sources(settings, requested, force=args.force)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if not sources:
        print(
            'No source to backfill: give --sources (or set '
            'PARTNERS_BACKFILL_SOURCES); the sources switched off for the '
            'harvest need --force.',
            file=sys.stderr,
        )
        return 2
    if args.reset:
        with Session(DBSession.get_bind()) as session:
            backfill.reset_sources(session, sources)
    summaries = backfill.backfill_partner_outings(
        settings,
        sources,
        floor=args.floor,
        steps=args.steps,
        pages=args.pages,
        details=args.details,
    )
    for summary in summaries:
        print(
            f'{summary["source"]}: {summary["status"]} '
            f'{summary["upserted"]} upserted, {summary["requests"]} requests, '
            f'cursor {summary.get("cursor")} {summary.get("detail") or ""}'
        )
    failed = [s for s in summaries if s['status'] in ('blocked', 'down', 'failing')]
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
