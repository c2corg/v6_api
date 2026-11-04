import logging
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from c2corg_api.models import DBSession
from c2corg_api.models.token import Token

log = logging.getLogger(__name__)


def purge_token(test_session=None):
    now = datetime.now(UTC)
    # a plain session bound to the engine of DBSession (it is configured by the
    # scheduler): `sessionmaker()()` alone has no bind and fails with SQLAlchemy 2
    session = test_session or sessionmaker(bind=DBSession.get_bind())()

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
