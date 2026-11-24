import logging

from sqlalchemy.orm import Session

from c2corg_api.avalanche_bulletins.store import prune_superseded
from c2corg_api.harvest.runner import prune_payloads
from c2corg_api.models import DBSession

log = logging.getLogger(__name__)


def prune_harvest():
    """Delete the old payloads, and the bulletins superseded the same day."""
    prune_payloads()
    with Session(DBSession.get_bind()) as session:
        count = prune_superseded(session)
        log.info('Pruning %d superseded avalanche bulletins', count)
        session.commit()
