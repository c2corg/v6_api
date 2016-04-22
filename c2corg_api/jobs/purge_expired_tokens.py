from c2corg_api.models.token import Token
from datetime import datetime
from sqlalchemy.orm import sessionmaker

import logging
log = logging.getLogger(__name__)


def purge_token(test_session=None):
    now = datetime.utcnow()
    session = sessionmaker()() if not test_session else test_session

    try:
        count = session.query(Token).filter(
                Token.expire <= now).delete(synchronize_session=False)

        log.info('Deleting %d expired token', count)
        if count > 0:
            session.commit()
    finally:
        if not test_session:
            session.close()
