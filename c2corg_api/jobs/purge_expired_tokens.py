import logging
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from c2corg_api.models.token import Token

log = logging.getLogger(__name__)


def purge_token(test_session=None):
    now = datetime.now(timezone.utc)
    session = sessionmaker()() if not test_session else test_session

    try:
        count = (
            session.query(Token)
            .filter(Token.expire <= now)
            .delete(synchronize_session=False)
        )

        log.info('Deleting %d expired token', count)
        if count > 0:
            session.commit()
    finally:
        if not test_session:
            session.close()
