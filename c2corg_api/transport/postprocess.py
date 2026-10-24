"""Post-process the imported GTFS feeds.

What is done once the feeds are imported (`import_gtfs` does it at the end):

1. the Navitia stops are linked to the GTFS stops (`link_stops.sql`);
2. the stops of the same place are grouped in clusters;
3. the lines that are in several feeds are hidden but one.

It can be done again alone, after an import, a change of the Navitia stops
(`scripts/public_transport/get_public_transports.sh` does the first step) or
a change of the thresholds of `dedup.py`:

    transport_postprocess <config_uri> [--report]

`--report` writes the groups of stops with different names, and the hidden
lines, to check the thresholds.
"""

import argparse
import logging

import transaction
from pyramid.paster import get_appsettings, setup_logging
from sqlalchemy import engine_from_config
from zope.sqlalchemy import mark_changed

from c2corg_api.models import Base, DBSession
from c2corg_api.transport.dedup import (
    cluster_transport_stops,
    hide_duplicate_lines,
    name_tokens,
)
from c2corg_api.transport.linking import link_transport_stops

log = logging.getLogger(__name__)


def postprocess(session):
    """Links, groups and hides.

    Returns what it found: {'linked': number, 'clusters': [...], 'hidden_lines':
    {hidden: kept}} The caller commits.
    """
    return {
        'linked': link_transport_stops(session),
        'clusters': cluster_transport_stops(session),
        'hidden_lines': hide_duplicate_lines(session),
    }


def report(found):
    """Return the groups to read to check the thresholds."""
    lines = []
    for anchor, members, anchor_name in found['clusters']:
        names = {frozenset(name_tokens(name)) for _, name, _ in members}
        names.add(frozenset(name_tokens(anchor_name)))
        if len(names) > 1:
            joined = ', '.join(
                f'"{name}" ({int(meters)} m)' for _, name, meters in members
            )
            lines.append(f'stop {anchor} "{anchor_name}" <- {joined}')
    lines.extend(
        f'line {hidden} hidden, duplicate of line {kept}'
        for hidden, kept in sorted(found['hidden_lines'].items())
    )
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('config_uri')
    parser.add_argument(
        '--report',
        action='store_true',
        help='write the groups of stops with different names and the hidden lines',
    )
    args = parser.parse_args(argv)

    setup_logging(args.config_uri)
    settings = get_appsettings(args.config_uri)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    with transaction.manager:
        found = postprocess(DBSession)
        # raw SQL does not mark the session as changed: without this, nothing
        # would be committed
        mark_changed(DBSession())

    if args.report:
        print('\n'.join(report(found)))
    clustered = sum(len(members) for _, members, _ in found['clusters'])
    print(
        f'{found["linked"]} stops linked to Navitia, '
        f'{clustered} stops in {len(found["clusters"])} clusters, '
        f'{len(found["hidden_lines"])} lines hidden'
    )


if __name__ == '__main__':
    main()
