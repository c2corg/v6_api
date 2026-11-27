"""The checks of the links to other sites (see c2corg_api.linkcheck)."""

from sqlalchemy.sql.schema import Column, ForeignKey, Index
from sqlalchemy.sql.sqltypes import DateTime, Integer, SmallInteger, String, Text

from c2corg_api.models import Base, schema, users_schema

# the statuses of a link: never checked yet, the page is there (maybe at
# another URL of the same site), it is now on another site, a parked domain,
# a page that changed completely or looks like spam, failing (not found, no
# such domain...) and dead once it failed long enough, not checked (refused
# by the robots.txt of the site, unusual port)
UNCHECKED = 'unchecked'
OK = 'ok'
MOVED = 'moved'
OFFSITE = 'offsite'
PARKED = 'parked'
SUSPECT = 'suspect'
FAILING = 'failing'
DEAD = 'dead'
BLOCKED = 'blocked'
STATUSES = (UNCHECKED, OK, MOVED, OFFSITE, PARKED, SUSPECT, FAILING, DEAD, BLOCKED)

# the reviews of the moderators: a link still leads to the right page, or
# its domain was taken over; a host whose links are all genuine
GENUINE = 'genuine'
TAKEN_OVER = 'taken_over'
TRUSTED = 'trusted'


class LinkHost(Base):
    """A site linked in texts: when it may be requested again, its robots.txt."""

    __tablename__ = 'link_hosts'

    host = Column(String(255), primary_key=True)

    # one request at a time per host, whichever process makes it
    next_request_at = Column(DateTime(timezone=True))

    # as received (None: none, allows everything), and when
    robots_txt = Column(Text)
    robots_fetched_at = Column(DateTime(timezone=True))

    # by a moderator: TRUSTED (its links are genuine, even if not checked)
    review = Column(String(20))
    reviewed_by = Column(Integer, ForeignKey(users_schema + '.user.id'))
    reviewed_at = Column(DateTime(timezone=True))

    __table_args__ = ({'schema': schema},)


class LinkCheck(Base):
    """The last check of a URL linked in the texts of collaborative documents."""

    # One row per URL, whatever the number of texts that link it (see
    # models.external_link). Created when a text links it, deleted some time
    # after no text does any more (last_seen_at).

    __tablename__ = 'link_checks'

    url = Column(Text, primary_key=True)

    host = Column(String(255), nullable=False)

    status = Column(String(20), nullable=False, default=UNCHECKED)

    # the HTTP status of the last answer, or the kind of error (dns, tls,
    # refused, timeout, private, too_many_redirects..., or home / login /
    # closed: a page redirected to the home page, to a login page, to the page
    # of a hosting platform saying the site is no more)
    http_status = Column(SmallInteger)
    error = Column(String(30))

    # where the redirections led, when elsewhere
    final_url = Column(Text)

    # the title of the page when first seen (or when reviewed genuine) and
    # now: a page whose title changed completely is suspect
    first_title = Column(String(300))
    last_title = Column(String(300))

    # consecutive failures, since: dead after a few, weeks apart
    failures = Column(SmallInteger, nullable=False, default=0)
    first_failure_at = Column(DateTime(timezone=True))

    last_ok_at = Column(DateTime(timezone=True))
    last_checked_at = Column(DateTime(timezone=True))
    next_check_at = Column(DateTime(timezone=True))

    # last time a text of a collaborative document linked it
    last_seen_at = Column(DateTime(timezone=True), nullable=False)

    # by a moderator: GENUINE (until the title changes completely) or TAKEN_OVER
    review = Column(String(20))
    reviewed_by = Column(Integer, ForeignKey(users_schema + '.user.id'))
    reviewed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index('ix_guidebook_link_checks_host', 'host'),
        Index('ix_guidebook_link_checks_next_check_at', 'next_check_at'),
        Index('ix_guidebook_link_checks_status', 'status'),
        {'schema': schema},
    )
