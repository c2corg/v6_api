"""Fixtures of the contract tests."""

from dataclasses import dataclass

import pytest

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.contract import Browser
from c2corg_api.tests.contract.documents import Documents, create_documents


@pytest.fixture
def browser(client, settings):
    """Send requests as a browser client does."""
    return Browser(client, settings)


@pytest.fixture
def documents(browser, user_ids) -> Documents:
    """Create one document of each type through the API."""
    return create_documents(browser, user_ids)


@dataclass
class StopareaLink:
    """A stop area near the waypoint of `documents`, and the link to it."""

    stoparea_id: int
    link_id: int


@pytest.fixture
def stoparea_link(session, documents) -> StopareaLink:
    """Add a stop area near the waypoint of `documents`."""
    stoparea = Stoparea(
        navitia_id='stop_area:SNCF:87747006',
        stoparea_name='Grenoble',
        line='TER',
        operator='SNCF',
        geom='SRID=3857;POINT(636150 5652000)',
    )
    session.add(stoparea)
    session.flush()
    link = WaypointStoparea(
        waypoint_id=documents.ids['waypoints'],
        stoparea_id=stoparea.stoparea_id,
        distance=123.456,
    )
    session.add(link)
    session.flush()
    return StopareaLink(stoparea.stoparea_id, link.waypoint_stoparea_id)
