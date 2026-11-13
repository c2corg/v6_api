import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from c2corg_api.models import DBSession
from c2corg_api.models.token import Token
from c2corg_api.security.discourse_client import get_discourse_client

log = logging.getLogger(__name__)

# between two forum logouts: each takes up to 2 requests, and the admin API
# of Discourse accepts 60 requests a minute
FORUM_LOGOUT_INTERVAL = 2


def purge_token(settings=None):
    """Delete the expired tokens, and close the forum session of their users."""
    now = datetime.now(UTC)

    # A plain session on the engine configured on DBSession by
    # c2corg_api/scripts/jobs/scheduler.py: DBSession itself cannot be committed
    # outside of the transaction manager, and `Session()` alone has no bind.
    with Session(DBSession.get_bind()) as session:
        expired = Token.expire <= now
        users = set(
            session.scalars(select(Token.userid).where(expired).distinct()).all()
        )
        count = session.query(Token).filter(expired).delete(synchronize_session=False)

        log.info('Deleting %d expired token', count)
        if count > 0:
            session.commit()

        # the users still logged in elsewhere keep their forum session
        logged_in = set(
            session.scalars(
                select(Token.userid).where(Token.userid.in_(users)).distinct()
            ).all()
        )

    if settings is not None:
        logout_from_forum(settings, sorted(users - logged_in))


def logout_from_forum(settings, user_ids, interval=FORUM_LOGOUT_INTERVAL):
    """Close the forum session of users whose c2c session expired."""
    # The forum keeps its own session (60 days by default), opened by the SSO
    # at the login: without this, it stays open after the c2c token expired.
    client = get_discourse_client(settings)
    for index, user_id in enumerate(user_ids):
        if index:
            time.sleep(interval)
        try:
            client.logout(user_id)
        except Exception:
            # e.g. a user who never went to the forum
            log.warning('Could not log out %d from the forum', user_id, exc_info=True)
    if user_ids:
        log.info('Logged out %d users from the forum', len(user_ids))
