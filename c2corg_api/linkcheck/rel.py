"""Which links to other sites the search engines may credit (no rel="nofollow ugc").

The links of the texts are written by users: by default rel="nofollow ugc"
(see markdown._mark_external_links), so that a domain taken over gains
nothing from camptocamp. A link known to be genuine is credited: checked
fine lately, reviewed genuine by a moderator, or of a site they trust.
Never a link taken over, gone or doubtful (dead, failing, parked, suspect).
The rendering (views.markdown.cook) and the invalidation of the cache of
the documents showing a link (when the checker or a review changes it) use
this same rule.
"""

import re
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, text

from c2corg_api.models.external_link import ExternalLink
from c2corg_api.models.link_check import (
    DEAD,
    FAILING,
    GENUINE,
    MOVED,
    OK,
    PARKED,
    SUSPECT,
    TAKEN_OVER,
    TRUSTED,
    LinkCheck,
    LinkHost,
)

# a check fine for that long credits the link (checked again every month)
CREDITED_FOR = timedelta(days=90)

# the statuses that never credit a link, whatever its review
NOT_CREDITED = (DEAD, FAILING, PARKED, SUSPECT)

# the http(s) addresses of a text, loosely: the URLs to look up (a link whose
# address is not found this way keeps rel="nofollow ugc")
_URL_RE = re.compile(r'https?://[^\s<>"\'\]\[)(|`]+', re.IGNORECASE)


def is_credited(check, host_review, now):
    """Tell whether a link may be credited, from its check (LinkCheck)."""
    if check is None:
        return host_review == TRUSTED
    if check.review == TAKEN_OVER or check.status in NOT_CREDITED:
        return False
    if check.review == GENUINE or host_review == TRUSTED:
        return True
    return (
        check.status in (OK, MOVED)
        and check.last_ok_at is not None
        and check.last_ok_at >= now - CREDITED_FOR
    )


def credited_condition(now):
    """Return the condition (SQL) that a checked link may be credited."""
    return and_(
        func.coalesce(LinkCheck.review, '') != TAKEN_OVER,
        LinkCheck.status.notin_(NOT_CREDITED),
        or_(
            func.coalesce(LinkCheck.review, '') == GENUINE,
            func.coalesce(LinkHost.review, '') == TRUSTED,
            and_(
                LinkCheck.status.in_((OK, MOVED)),
                LinkCheck.last_ok_at >= now - CREDITED_FOR,
            ),
        ),
    )


def text_urls(texts):
    """Return the http(s) addresses written in texts, loosely (a set)."""
    urls = set()
    for value in texts:
        if isinstance(value, str):
            urls.update(match.rstrip('.,;:!?') for match in _URL_RE.findall(value))
    return urls


def credited_urls(session, urls, now):
    """Return the URLs among these that may be credited (a set)."""
    urls = {url for url in urls if len(url.encode()) <= 2000}
    if not urls:
        return set()
    return set(
        session.execute(
            select(LinkCheck.url)
            .outerjoin(LinkHost, LinkHost.host == LinkCheck.host)
            .where(LinkCheck.url.in_(urls), credited_condition(now))
        ).scalars()
    )


def documents_linking(session, urls):
    """Return the ids of the documents whose texts link these URLs (a set)."""
    if not urls:
        return set()
    return set(
        session.execute(
            select(ExternalLink.document_id).where(ExternalLink.url.in_(list(urls)))
        ).scalars()
    )


def invalidate(session, urls):
    """Bump the cache version of the documents linking these URLs (rendered again)."""
    ids = sorted(documents_linking(session, urls))
    if ids:
        session.execute(
            text('SELECT guidebook.increment_cache_versions(:document_ids)'),
            {'document_ids': ids},
        )
    return len(ids)
