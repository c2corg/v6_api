"""The GPX tracks of the partner outings: a slow second phase of a harvest run.

After the outings of a source are stored (`harvest_partner_outings`), a few of
its outings with a `gpx_url` and no track yet get their GPX file read, newest
outings first: at most `partners.tracks_per_run` files (3 by default, 0 turns
the phase off), one every `partners.tracks_interval_seconds` (10 s), with a
transport and a request budget of their own, so the JSON harvest never waits
for them and a slow file never makes the source `down`.

Only the points are kept (`partners.gpx`): no time, heart rate, name or author.
A file the site fails to serve (5xx, timeout) is `failed` and tried again later,
at most MAX_ATTEMPTS times, waiting 1, 2, 4... hours; a file that is not a
usable GPX (too big, not XML, no line, 404) is `invalid` and not tried again
unless the outing links to another file. A block (403, challenge) stops the
phase for this run.

Only the sources that declare a licence for their tracks (`TRACK_LICENCE` on
the adapter: gulliver.it, CC BY-NC-ND) have this phase. Backfilling the tracks
of older outings needs nothing more than more runs (or a bigger budget): the
outings are kept, and the phase picks the newest outings without a track.
"""

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from c2corg_api.models.partner_outing import PartnerTrack
from c2corg_api.partners import gpx
from c2corg_api.partners.adapter import SourceBlocked, SourceDown
from c2corg_api.partners.model import RateLimit
from c2corg_api.partners.transport import FixtureTransport, HttpTransport

log = logging.getLogger(__name__)

DEFAULT_PER_RUN = 3
DEFAULT_INTERVAL_S = 10.0
MIN_INTERVAL_S = 10.0
TIMEOUT_S = 30.0
MAX_ATTEMPTS = 4
# the fixtures of the tracks of a source: `<fixtures>/<source>_tracks/`
FIXTURES_SUFFIX = '_tracks'
DETAIL_LENGTH = 200


def tracks_per_run(settings):
    value = str(settings.get('partners.tracks_per_run', '') or '').strip()
    return max(int(value), 0) if value else DEFAULT_PER_RUN


def _interval(settings):
    value = str(settings.get('partners.tracks_interval_seconds', '') or '').strip()
    return max(float(value), MIN_INTERVAL_S) if value else DEFAULT_INTERVAL_S


def has_tracks(adapter_cls):
    return bool(getattr(adapter_cls, 'TRACK_LICENCE', None))


def track_transport(adapter_cls, settings, fixtures_dir=None):
    """Return the transport of the tracks of a source, or None (no phase).

    `http`: its own `HttpTransport` (budget: the files of a run, at least the
    interval apart, bodies cut over `gpx.MAX_BYTES`). `fixtures`: the
    directory `<source>_tracks` when there is one (synthetic GPX files, only
    when `partners.allow_synthetic`), else no phase.
    """
    per_run = tracks_per_run(settings)
    if per_run == 0 or not has_tracks(adapter_cls):
        return None
    rate = RateLimit(_interval(settings), per_run, TIMEOUT_S)
    kind = str(settings.get('partners.transport') or 'http').strip().lower()
    if kind == 'http':
        return HttpTransport(rate, max_bytes=gpx.MAX_BYTES)
    name = adapter_cls.name + FIXTURES_SUFFIX
    if fixtures_dir is None or not (Path(fixtures_dir) / name).is_dir():
        return None
    transport = FixtureTransport(Path(fixtures_dir), name, rate=rate)
    allowed = str(settings.get('partners.allow_synthetic') or '').lower() == 'true'
    if transport.synthetic and not allowed:
        log.info('Partner tracks %s: synthetic fixtures not allowed', name)
        return None
    return transport


def _due(session, source, now, limit):
    """Return the outings whose GPX file is to be read, newest first."""
    rows = session.execute(
        text(
            """
            SELECT p.external_id, p.gpx_url
            FROM guidebook.partner_outings p
            LEFT JOIN guidebook.partner_tracks t
                ON t.source = p.source AND t.external_id = p.external_id
            WHERE p.source = :source AND p.gpx_url IS NOT NULL
              AND (t.id IS NULL
                   OR t.gpx_url <> p.gpx_url
                   OR (t.status = 'failed' AND t.attempts < :max_attempts
                       AND t.last_attempt_at < :now - make_interval(
                           hours => power(2, t.attempts - 1)::int)))
            ORDER BY p.date DESC, p.external_id DESC
            LIMIT :limit"""
        ),
        {
            'source': source,
            'now': now,
            'limit': limit,
            'max_attempts': MAX_ATTEMPTS,
        },
    )
    return [(row.external_id, row.gpx_url) for row in rows]


def _row(session, source, external_id, url, now):
    track = (
        session.query(PartnerTrack)
        .filter_by(source=source, external_id=external_id)
        .one_or_none()
    )
    if track is None:
        track = PartnerTrack(source=source, external_id=external_id, attempts=0)
        session.add(track)
    elif track.gpx_url != url:
        track.attempts = 0  # another file: a fresh start
    track.gpx_url = url
    track.last_attempt_at = now
    track.attempts = (track.attempts or 0) + 1
    return track


def _store(session, track, parsed, now):
    track.status = 'ok'
    track.detail = None
    track.fetched_at = now
    track.point_count = parsed.point_count
    track.simplified = parsed.simplified
    session.flush()
    session.execute(
        text(
            """
            UPDATE guidebook.partner_tracks SET geom =
                ST_Transform(ST_GeomFromText(:wkt, 4326), 3857)
            WHERE id = :id"""
        ),
        {'wkt': gpx.wkt(parsed), 'id': track.id},
    )


def _fail(track, status, detail):
    track.status = status
    track.detail = detail[:DETAIL_LENGTH]
    if status == 'invalid':
        track.geom = None


def harvest_tracks(session, adapter_cls, transport, now, settings):
    """Read the due GPX files of a source; return `{'ok': n, 'failed': n, ...}`.

    Commits each file on its own. Never raises for a file; a block stops the
    phase (SourceBlocked is caught and logged).
    """
    counts = {'ok': 0, 'failed': 0, 'invalid': 0}
    source = adapter_cls.name
    due = _due(session, source, now, transport.rate.max_requests_per_run)
    for external_id, url in due:
        track = _row(session, source, external_id, url, now)
        try:
            response = transport.get(url)
        except SourceBlocked as e:
            _fail(track, 'failed', f'blocked: {e}')
            counts['failed'] += 1
            session.commit()
            log.warning('Partner tracks %s: blocked, stopped: %s', source, e)
            break
        except SourceDown as e:
            _fail(track, 'failed', str(e))
            counts['failed'] += 1
            session.commit()
            if 'budget' in str(e):
                break
            continue
        if response.status != 200:
            _fail(track, 'invalid', f'HTTP {response.status}')
            counts['invalid'] += 1
        else:
            try:
                parsed = gpx.parse(response.body)
            except gpx.GpxError as e:
                _fail(track, 'invalid', str(e))
                counts['invalid'] += 1
            else:
                _store(session, track, parsed, now)
                counts['ok'] += 1
        session.commit()
    if due:
        log.info('Partner tracks %s: %s', source, counts)
    return counts


def retry_delay(attempts):
    """Return the wait before a `failed` file is tried again."""
    return timedelta(hours=2 ** max(attempts - 1, 0))
