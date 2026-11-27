"""The links to other sites of the collaborative documents, as checked (moderation).

The link checker of the scheduler (c2corg_api.linkcheck) keeps
guidebook.link_checks: the moderators list the links that need a look, by
host, with the documents showing them, and review them: a link still
genuine (it may lose rel="nofollow ugc" later), a domain taken over, a host
trusted; or ask for a check again.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, array_agg

from c2corg_api.linkcheck.checker import RECHECK_AT
from c2corg_api.models import DBSession
from c2corg_api.models.document import Document
from c2corg_api.models.external_link import ExternalLink
from c2corg_api.models.link_check import (
    BLOCKED,
    DEAD,
    FAILING,
    GENUINE,
    MOVED,
    OFFSITE,
    OK,
    PARKED,
    STATUSES,
    SUSPECT,
    TAKEN_OVER,
    TRUSTED,
    UNCHECKED,
    LinkCheck,
    LinkHost,
)
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import OneOf, Str
from c2corg_api.views.document_links import collaborative
from c2corg_api.views.image_embeds import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    document_locales,
    title_fields,
)
from c2corg_api.views.resource import write

# listed by default: the links that need a look
DEFAULT_STATUSES = (DEAD, FAILING, PARKED, SUSPECT, OFFSITE)

# the order of the statuses in the counts
STATUS_ORDER = (DEAD, FAILING, PARKED, SUSPECT, OFFSITE, MOVED, BLOCKED, OK, UNCHECKED)

# the documents shown per link at most (the others are counted)
DOCUMENTS_MAX = 20


def _shown_urls():
    """Select the URLs linked by collaborative documents shown (not merged)."""
    return (
        select(ExternalLink.url)
        .join(Document, Document.document_id == ExternalLink.document_id)
        .where(Document.redirects_to.is_(None), collaborative(Document))
    )


def _conditions(host=None, reviewed=False):
    """Return the conditions on the checks (SQL), but their status."""
    conditions = [LinkCheck.url.in_(_shown_urls())]
    if host:
        conditions.append(LinkCheck.host == host.lower())
    # reviewed: a link said genuine, or one of a trusted host (no takeover);
    # a link taken over stays listed until removed. A review does not keep a
    # page from being gone: the dead and failing links are listed either way
    is_reviewed = or_(
        func.coalesce(LinkCheck.review, '') == GENUINE,
        func.coalesce(LinkHost.review, '') == TRUSTED,
    )
    failed = LinkCheck.status.in_((DEAD, FAILING))
    conditions.append(is_reviewed if reviewed else or_(~is_reviewed, failed))
    return conditions


def list_external_links(statuses, host, reviewed, offset, limit):
    """Return the checked links to other sites of collaborative documents, by host."""
    base = select(LinkCheck).join(
        LinkHost, LinkHost.host == LinkCheck.host, isouter=True
    )
    conditions = _conditions(host, reviewed)
    counts = dict(
        DBSession.execute(
            base.with_only_columns(LinkCheck.status, func.count())
            .where(*conditions)
            .group_by(LinkCheck.status)
        ).all()
    )
    selected = [*conditions, LinkCheck.status.in_(statuses)]
    total = DBSession.execute(
        base.with_only_columns(func.count()).where(*selected)
    ).scalar()
    rows = DBSession.execute(
        base.add_columns(LinkHost.review.label('host_review'))
        .where(*selected)
        .order_by(LinkCheck.host, LinkCheck.url)
        .offset(offset)
        .limit(limit)
    ).all()
    documents = _documents([row.LinkCheck.url for row in rows])
    titles = document_locales(
        {d['document_id'] for docs in documents.values() for d in docs}
    )
    return {
        'total': total,
        'counts': {status: counts.get(status, 0) for status in STATUS_ORDER},
        'links': [
            _link(
                row.LinkCheck,
                row.host_review,
                documents.get(row.LinkCheck.url, []),
                titles,
            )
            for row in rows
        ],
    }


def _documents(urls):
    """Return the collaborative documents linking each URL: {url: [doc]}."""
    if not urls:
        return {}
    rows = DBSession.execute(
        select(
            ExternalLink.url,
            ExternalLink.document_id,
            Document.type,
            array_agg(
                aggregate_order_by(ExternalLink.lang.distinct(), ExternalLink.lang)
            ),
        )
        .join(Document, Document.document_id == ExternalLink.document_id)
        .where(
            ExternalLink.url.in_(urls),
            Document.redirects_to.is_(None),
            collaborative(Document),
        )
        .group_by(ExternalLink.url, ExternalLink.document_id, Document.type)
        .order_by(ExternalLink.url, ExternalLink.document_id.desc())
    ).all()
    documents = {}
    for url, document_id, document_type, langs in rows:
        documents.setdefault(url, []).append(
            {'document_id': document_id, 'document_type': document_type, 'langs': langs}
        )
    return documents


def _iso(value):
    return value.isoformat() if value else None


def _link(check, host_review, documents, titles):
    return {
        'url': check.url,
        'host': check.host,
        'host_review': host_review,
        'status': check.status,
        'http_status': check.http_status,
        # the kind of error (dns, tls, home, login...)
        'error': check.error,
        'final_url': check.final_url,
        'first_title': check.first_title,
        'last_title': check.last_title,
        'failures': check.failures,
        'first_failure_at': _iso(check.first_failure_at),
        'last_ok_at': _iso(check.last_ok_at),
        'last_checked_at': _iso(check.last_checked_at),
        'next_check_at': _iso(check.next_check_at),
        'review': check.review,
        'reviewed_at': _iso(check.reviewed_at),
        'documents_count': len(documents),
        'documents': [
            {**document, **title_fields(titles, document['document_id'])}
            for document in documents[:DOCUMENTS_MAX]
        ],
    }


def _statuses(value):
    """Return the statuses asked (comma separated), else the default ones."""
    if not value:
        return list(DEFAULT_STATUSES)
    return [status for status in value.split(',') if status in STATUSES]


def read_external_links(request):
    """List the checked links to other sites of collaborative documents."""
    # GET /documents/external-links?status=dead,failing&host=&reviewed=&offset=&limit=
    validated = request.validated
    return list_external_links(
        _statuses(validated.get('status')),
        validated.get('host'),
        bool(validated.get('reviewed')),
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
    )


class LinkReviewSchema(Schema):
    url: Str(max_length=2000, min_length=1)
    # None: no review any more
    review: OneOf([GENUINE, TAKEN_OVER]) = None


class HostReviewSchema(Schema):
    host: Str(max_length=255, min_length=1)
    review: OneOf([TRUSTED]) = None


class RecheckSchema(Schema):
    url: Str(max_length=2000, min_length=1)


def _validate_url(request, **kwargs):
    """Check that the URL is one of the link checks."""
    url = request.validated.get('url')
    if url is not None and DBSession.get(LinkCheck, url) is None:
        request.errors.add('body', 'url', 'not a checked link')


def _validate_host(request, **kwargs):
    """Check that the host is one of the hosts of the link checks."""
    host = request.validated.get('host')
    if host is not None and DBSession.get(LinkHost, host.lower()) is None:
        request.errors.add('body', 'host', 'not a checked host')


def _set_review(row, review, user_id):
    row.review = review
    row.reviewed_by = user_id if review else None
    row.reviewed_at = datetime.now(UTC) if review else None


@write(
    validators=[body_validator(LinkReviewSchema), _validate_url],
    permission='moderator',
    json=True,
)
def review_external_link(request):
    """Review a link: still genuine, or its domain taken over (or no review)."""
    # `POST` `/documents/external-links/review` {'url': ..., 'review': 'genuine'}
    check = DBSession.get(LinkCheck, request.validated['url'])
    review = request.validated.get('review')
    _set_review(check, review, request.authenticated_userid)
    if review == GENUINE and check.last_title:
        # genuine until its title changes completely: from the one seen now
        check.first_title = check.last_title
    DBSession.flush()
    return {'url': check.url, 'review': check.review}


@write(
    validators=[body_validator(HostReviewSchema), _validate_host],
    permission='moderator',
    json=True,
)
def review_external_host(request):
    """Trust a host: its links are genuine, even those not checked (or no review)."""
    # `POST` `/documents/external-links/review-host` {'host': ..., 'review': 'trusted'}
    host = DBSession.get(LinkHost, request.validated['host'].lower())
    _set_review(host, request.validated.get('review'), request.authenticated_userid)
    DBSession.flush()
    return {'host': host.host, 'review': host.review}


@write(
    validators=[body_validator(RecheckSchema), _validate_url],
    permission='moderator',
    json=True,
)
def recheck_external_link(request):
    """Check a link again at the next run of the checker."""
    # `POST` `/documents/external-links/recheck` {'url': ...}
    check = DBSession.get(LinkCheck, request.validated['url'])
    # before the others, even the never checked ones (see linkcheck.checker)
    check.next_check_at = RECHECK_AT
    DBSession.flush()
    return {'url': check.url, 'next_check_at': _iso(check.next_check_at)}
