"""
Imports the GTFS feeds listed in `feeds.json` in the database.

    import_gtfs <config_uri> [--feed <id> ...] [--force]
"""

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime

import requests
import transaction
from pyramid.paster import get_appsettings, setup_logging
from shapely import wkt
from sqlalchemy import engine_from_config, text
from zope.sqlalchemy import mark_changed

from c2corg_api.models import Base, DBSession
from c2corg_api.models.transport import TransportFeed, TransportLine, TransportStop
from c2corg_api.transport import gtfs
from c2corg_api.transport.postprocess import postprocess

log = logging.getLogger(__name__)

FEEDS_FILE = os.path.join(os.path.dirname(__file__), 'feeds.json')
DOWNLOAD_TIMEOUT = 120  # seconds
INSERT_BATCH = 2000


def load_feeds():
    with open(FEEDS_FILE, encoding='utf-8') as f:
        return json.load(f)


def download(url, path):
    """Download the archive, returns its checksum."""
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                digest.update(chunk)
                f.write(chunk)
    return digest.hexdigest()


def _ewkt(geom):
    """Return the geometry as the database expects it (EPSG:3857, in cm)."""
    return 'SRID=3857;' + wkt.dumps(geom, rounding_precision=2)


def _insert(session, table, rows):
    for i in range(0, len(rows), INSERT_BATCH):
        session.execute(table.insert(), rows[i : i + INSERT_BATCH])


def save(session, feed, parsed, checksum):
    """Replace the lines and stops of a feed.

    Everything happens in the transaction of the session: readers never see a partial
    import.
    """
    record = session.get(TransportFeed, feed['id'])
    if record is None:
        record = TransportFeed(feed_id=feed['id'])
        session.add(record)
    record.name = feed['name']
    record.url = feed['url']
    record.license = feed['license']
    record.attribution = feed['attribution']
    record.checksum = checksum
    record.imported_at = datetime.now(UTC)
    record.status = 'ok'
    session.flush()

    # what was grouped with the stops and lines of this feed is alone until the
    # next postprocess
    session.execute(
        text("""
        UPDATE guidebook.transport_stops SET cluster_id = stop_pk
        WHERE cluster_id IN (
            SELECT stop_pk FROM guidebook.transport_stops
            WHERE feed_id = :feed)
    """),
        {'feed': feed['id']},
    )
    session.execute(
        text("""
        UPDATE guidebook.transport_lines SET duplicate_of = NULL
        WHERE duplicate_of IN (
            SELECT line_id FROM guidebook.transport_lines
            WHERE feed_id = :feed)
    """),
        {'feed': feed['id']},
    )
    session.query(TransportLine).filter_by(feed_id=feed['id']).delete()
    session.query(TransportStop).filter_by(feed_id=feed['id']).delete()

    _insert(
        session,
        TransportLine.__table__,
        [
            {
                'feed_id': feed['id'],
                'route_id': line['route_id'],
                'short_name': line['short_name'],
                'long_name': line['long_name'],
                'mode': line['mode'],
                'color': line['color'],
                'text_color': line['text_color'],
                'operator': line['operator'],
                'url': line['url'],
                'geom': _ewkt(line['geom']) if line['geom'] is not None else None,
                'details': line['details'],
            }
            for line in parsed['lines']
        ],
    )
    _insert(
        session,
        TransportStop.__table__,
        [
            {
                'feed_id': feed['id'],
                'stop_id': stop['stop_id'],
                'name': stop['name'],
                'mode': stop['mode'],
                'geom': _ewkt(stop['geom']),
                'ref_ids': stop['ref_ids'],
                'navitia_ids': [],
                'details': stop['details'],
            }
            for stop in parsed['stops']
        ],
    )
    # alone, until the postprocess
    session.execute(
        text("""
        UPDATE guidebook.transport_stops SET cluster_id = stop_pk
        WHERE feed_id = :feed
    """),
        {'feed': feed['id']},
    )


def import_feed(session, feed, force=False, today=None):
    """Download and imports a feed, unless it did not change since the last import.

    Returns True if the feed was imported.
    """
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, 'gtfs.zip')
        checksum = download(feed['url'], path)

        record = session.get(TransportFeed, feed['id'])
        if (
            not force
            and record is not None
            and record.checksum == checksum
            and record.status == 'ok'
        ):
            log.info('Feed %s did not change', feed['id'])
            return False

        parsed = gtfs.parse(path, today)

    save(session, feed, parsed, checksum)
    log.info(
        'Feed %s imported: %d lines, %d stops',
        feed['id'],
        len(parsed['lines']),
        len(parsed['stops']),
    )
    return True


def import_feeds(session, feed_ids=None, force=False):
    """Import the feeds, then link the Navitia stops.

    Imports the feeds one after the other (a failing feed does not prevent
    the others), then links the Navitia stops. The caller commits.
    """
    imported = 0
    for feed in load_feeds():
        if feed_ids and feed['id'] not in feed_ids:
            continue
        try:
            with session.begin_nested():
                imported += import_feed(session, feed, force)
        except Exception:
            log.exception('Import of the feed %s failed', feed['id'])
    postprocess(session)
    return imported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config_uri')
    parser.add_argument(
        '--feed',
        action='append',
        dest='feeds',
        help='only import this feed (can be repeated)',
    )
    parser.add_argument(
        '--force', action='store_true', help='import even if the feed did not change'
    )
    args = parser.parse_args(argv)

    setup_logging(args.config_uri)
    settings = get_appsettings(args.config_uri)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    with transaction.manager:
        import_feeds(DBSession, args.feeds, args.force)
        # the links are written with raw SQL, which does not mark the
        # session as changed: without this, they would not be committed
        mark_changed(DBSession())


if __name__ == '__main__':
    main()
