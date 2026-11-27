"""Check the links to other sites of the texts of collaborative documents.

Calmly: a few requests per run (link_checker.requests_per_run), one URL per
host per run, the robots.txt of the sites respected. A URL is checked again
a month after it was fine, a week after it failed; dead after failing a few
times, weeks apart (see apply). Nothing is shown yet: the moderators will
review the results, and genuine links will lose rel="nofollow ugc".
"""

import logging
import secrets
import time
import urllib.robotparser
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.orm import Session

from c2corg_api.linkcheck import classify as c
from c2corg_api.linkcheck.fetch import USER_AGENT, fetch
from c2corg_api.models.document import Document
from c2corg_api.models.external_link import ExternalLink
from c2corg_api.models.link_check import (
    BLOCKED,
    DEAD,
    FAILING,
    GENUINE,
    UNCHECKED,
    LinkCheck,
    LinkHost,
)
from c2corg_api.views.document_links import collaborative

log = logging.getLogger(__name__)

REQUESTS_PER_RUN = 10

# a key of pg_try_advisory_lock: one run at a time, whatever the processes
_LOCK_KEY = 0x6C696E6B  # "link"

OK_INTERVAL = timedelta(days=30)
FAILING_INTERVAL = timedelta(days=7)
DEAD_INTERVAL = timedelta(days=90)
ROBOTS_INTERVAL = timedelta(days=7)
# between two requests to a host
HOST_INTERVAL = timedelta(minutes=1)
# a host whose robots.txt could not be read is tried again later
HOST_RETRY = timedelta(hours=6)
# dead: that many consecutive failures, the first one that long before
DEAD_FAILURES = 3
DEAD_AFTER = timedelta(days=14)
# a URL no text links any more is forgotten after
FORGET_AFTER = timedelta(days=90)

# a site reachable when the network works, checked before each run: an
# outage of the network or of the DNS must not count as failures
CANARY_URL = 'https://www.wikipedia.org/robots.txt'


# the system's random source (Bandit B311 on the random module)
_random = secrets.SystemRandom()


def _jitter(interval):
    """Spread the checks: ±20 %."""
    return interval * _random.uniform(0.8, 1.2)


def sync_link_checks(session, now):
    """Add the URLs newly linked by collaborative documents, forget the old ones."""
    # (added or seen again, forgotten). The documents shown: not merged (a
    # deleted document has no locale any more, so no link).
    urls = (
        select(ExternalLink.url, func.min(ExternalLink.host).label('host'))
        .join(Document, Document.document_id == ExternalLink.document_id)
        .where(Document.redirects_to.is_(None), collaborative(Document))
        .group_by(ExternalLink.url)
    )
    rows = session.execute(urls).all()
    seen = 0
    for start in range(0, len(rows), 1000):
        batch = rows[start : start + 1000]
        statement = insert(LinkCheck).values(
            [
                {
                    'url': url,
                    'host': host,
                    'status': UNCHECKED,
                    'failures': 0,
                    'last_seen_at': now,
                }
                for url, host in batch
            ]
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[LinkCheck.url],
                set_={'last_seen_at': statement.excluded.last_seen_at},
            )
        )
        hosts = sorted({host for _, host in batch})
        session.execute(
            insert(LinkHost)
            .values([{'host': host} for host in hosts])
            .on_conflict_do_nothing(index_elements=[LinkHost.host])
        )
        seen += len(batch)
    forgotten = (
        session.query(LinkCheck)
        .filter(LinkCheck.last_seen_at < now - FORGET_AFTER)
        .delete(synchronize_session=False)
    )
    return seen, forgotten


def due_checks(session, now, limit):
    """Return the URLs to check now: one per host, the most overdue first."""
    # never checked first, then by date
    order = (LinkCheck.next_check_at.is_(None).desc(), LinkCheck.next_check_at)
    per_host = (
        select(LinkCheck.url)
        .join(LinkHost, LinkHost.host == LinkCheck.host)
        .where(
            or_(LinkCheck.next_check_at.is_(None), LinkCheck.next_check_at <= now),
            or_(LinkHost.next_request_at.is_(None), LinkHost.next_request_at <= now),
        )
        .ext(distinct_on(LinkCheck.host))
        .order_by(LinkCheck.host, *order, LinkCheck.url)
        .subquery()
    )
    return (
        session.query(LinkCheck)
        .filter(LinkCheck.url.in_(select(per_host.c.url)))
        .order_by(*order, LinkCheck.url)
        .limit(limit)
        .all()
    )


def _robots_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))


def robots_allow(host_row, url, now):
    """Tell whether robots.txt lets us check the URL; None: unknown (try later)."""
    # (allowed, requested): the robots.txt is read again after a week. As
    # Google: none (4xx) allows everything; unreachable or 5xx: try later.
    requested = False
    fetched_at = host_row.robots_fetched_at
    if fetched_at is None or fetched_at < now - ROBOTS_INTERVAL:
        answer = fetch(_robots_url(url))
        requested = True
        status = answer.http_status
        if c.classify(url, answer) in c.FAILURES and answer.error:
            # no such domain, a private address...: the check of the page
            # will tell (a failure)
            return True, requested
        if answer.error or status is None or status >= 500:
            return None, requested
        content_type = answer.content_type.lower()
        # a robots.txt answered with a page (an error page...) is no robots.txt
        if 200 <= status < 300 and 'html' not in content_type:
            host_row.robots_txt = answer.text
        else:
            host_row.robots_txt = None
        host_row.robots_fetched_at = now
    parser = urllib.robotparser.RobotFileParser()
    parser.parse((host_row.robots_txt or '').splitlines())
    return parser.can_fetch(USER_AGENT, url), requested


def apply(check, outcome, answer, now):
    """Record the outcome of a check of a URL (models.link_check.LinkCheck)."""
    check.last_checked_at = now
    if answer is not None:
        check.http_status = answer.http_status
        check.error = answer.error
        check.final_url = answer.final_url if answer.final_url != check.url else None
        check.last_title = answer.title
    if outcome in c.FAILURES:
        if outcome != c.FAILURE:
            # why, the answer being fine: redirected to the home page...
            check.error = outcome
        check.failures = (check.failures or 0) + 1
        check.first_failure_at = check.first_failure_at or now
        dead = (
            check.failures >= DEAD_FAILURES
            and now - check.first_failure_at >= DEAD_AFTER
        )
        check.status = DEAD if dead else FAILING
        check.next_check_at = now + _jitter(DEAD_INTERVAL if dead else FAILING_INTERVAL)
        return
    if outcome == c.INCONCLUSIVE:
        # the status stays: a site down for a while, blocking us...
        check.next_check_at = now + _jitter(FAILING_INTERVAL)
        return
    check.next_check_at = now + _jitter(OK_INTERVAL)
    if outcome == c.BLOCKED:
        check.status = BLOCKED
        return
    check.failures = 0
    check.first_failure_at = None
    check.status = outcome
    if outcome in (c.OK, c.MOVED):
        check.last_ok_at = now
        if check.first_title is None:
            check.first_title = answer.title
    elif outcome == c.SUSPECT and check.review == GENUINE:
        # reviewed genuine until the page changes completely
        check.review = None
        check.reviewed_by = None
        check.reviewed_at = None


def check_link(session, check, host_row, now):
    """Check one URL (robots.txt first); return the number of requests made."""
    allowed, requests = robots_allow(host_row, check.url, now)
    if allowed is None:
        host_row.next_request_at = now + HOST_RETRY
        return requests
    if not allowed:
        apply(check, c.BLOCKED, None, now)
    else:
        if requests:
            # one request per second to a host
            time.sleep(1)
        answer = fetch(check.url)
        requests += 1
        apply(check, c.classify(check.url, answer, check.first_title), answer, now)
    host_row.next_request_at = now + HOST_INTERVAL
    return requests


def _postpone(session, url, host, now):
    """Check a URL again later, after an unexpected error (logged)."""
    session.query(LinkCheck).filter(LinkCheck.url == url).update(
        {LinkCheck.next_check_at: now + FAILING_INTERVAL}, synchronize_session=False
    )
    session.query(LinkHost).filter(LinkHost.host == host).update(
        {LinkHost.next_request_at: now + HOST_INTERVAL}, synchronize_session=False
    )
    session.commit()


def network_ok():
    """Tell whether a well-known site answers: else the run is skipped."""
    return fetch(CANARY_URL, read_body=False).http_status is not None


def run(bind, requests_per_run=REQUESTS_PER_RUN, now=None):
    """Sync the URLs, check the due ones; return the number of requests made."""
    # One run at a time (an advisory lock held by a connection of its own);
    # each URL checked is committed at once.
    with bind.connect() as lock:
        if not lock.execute(
            text('select pg_try_advisory_lock(:key)'), {'key': _LOCK_KEY}
        ).scalar():
            log.info('Link checker: another run is going on')
            return 0
        try:
            return _run(bind, requests_per_run, now)
        finally:
            lock.execute(text('select pg_advisory_unlock(:key)'), {'key': _LOCK_KEY})
            lock.commit()


def _run(bind, requests_per_run, now):
    with Session(bind) as session:
        return run_in(session, requests_per_run, now)


def run_in(session, requests_per_run, now=None):
    """Sync the URLs and check the due ones in a session (each URL committed)."""
    start = now or datetime.now(UTC)
    seen, forgotten = sync_link_checks(session, start)
    session.commit()
    log.info('Link checker: %d URLs linked, %d forgotten', seen, forgotten)
    if not network_ok():
        log.warning('Link checker: the network does not answer, no check')
        return 0
    requests = 0
    for check in due_checks(session, start, requests_per_run):
        if requests >= requests_per_run:
            break
        url, host = check.url, check.host
        try:
            host_row = session.get(LinkHost, host)
            requests += check_link(session, check, host_row, now or datetime.now(UTC))
            session.commit()
        except Exception:
            # one odd page must not stop the runs: it waits, the others go on
            log.exception('Link checker: checking %s failed', url)
            session.rollback()
            _postpone(session, url, host, now or datetime.now(UTC))
    log.info('Link checker: %d requests', requests)
    return requests
