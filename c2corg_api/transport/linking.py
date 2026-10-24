"""Link the Navitia stops to the imported GTFS stops.

Links the Navitia stops (`guidebook.stopareas`) to the imported GTFS stops
(`guidebook.transport_stops`), so that a stop of a waypoint shows its
timetables and lines.

The SQL is in `link_stops.sql`, shared with the Navitia import script
(`scripts/public_transport/get_public_transports.sh`): the links have to be
computed again after each import of GTFS feeds and after each import of
Navitia stops.
"""

import logging
import os
import re

from sqlalchemy import text

from c2corg_api.transport.settings import env_int

log = logging.getLogger(__name__)

SQL_FILE = os.path.join(os.path.dirname(__file__), 'link_stops.sql')

# a Navitia stop closer than this (meters) to a GTFS stop served by one of
# its lines is the same stop (the variable `TRANSPORT_LINK_DISTANCE` of the
# environment, see `.env`)
MAX_DISTANCE = env_int('TRANSPORT_LINK_DISTANCE', 50, minimum=0)


def _statements():
    with open(SQL_FILE, encoding='utf-8') as f:
        sql = f.read()
    sql = re.sub(r'^--.*$', '', sql, flags=re.MULTILINE)
    return [s.strip() for s in re.split(r';\s*$', sql, flags=re.MULTILINE) if s.strip()]


def link_transport_stops(session):
    """Recomputes `transport_stops.navitia_ids`, returns the linked count."""
    reset, by_id, by_line = _statements()
    session.execute(text(reset))
    linked_by_id = session.execute(text(by_id)).rowcount
    linked_by_line = session.execute(
        text(by_line), {'max_distance': MAX_DISTANCE}
    ).rowcount
    log.info(
        'Linked %d GTFS stops by id, %d by line and distance',
        linked_by_id,
        linked_by_line,
    )
    return linked_by_id + linked_by_line
