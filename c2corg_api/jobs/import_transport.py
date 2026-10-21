import logging

import transaction
from zope.sqlalchemy import mark_changed

from c2corg_api.models import DBSession
from c2corg_api.transport.importer import import_feeds

log = logging.getLogger(__name__)


def import_transport():
    """Imports the GTFS feeds that changed, then links the Navitia stops."""
    with transaction.manager:
        imported = import_feeds(DBSession)
        # the links are written with raw SQL, which does not mark the
        # session as changed: without this, they would not be committed
        mark_changed(DBSession())
    log.info('%d GTFS feeds imported', imported)
