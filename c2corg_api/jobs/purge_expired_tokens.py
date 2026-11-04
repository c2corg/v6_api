import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from c2corg_api.models import DBSession
from c2corg_api.models.token import Token

log = logging.getLogger(__name__)


def purge_token():
    now = datetime.now(UTC)

    # A plain session on the engine configured on DBSession by
    # c2corg_api/scripts/jobs/scheduler.py: DBSession itself cannot be committed
    # outside of the transaction manager, and `Session()` alone has no bind.
    with Session(DBSession.get_bind()) as session:
        count = (
            session.query(Token)
            .filter(Token.expire <= now)
            .delete(synchronize_session=False)
        )

        log.info('Deleting %d expired token', count)
        if count > 0:
            session.commit()
