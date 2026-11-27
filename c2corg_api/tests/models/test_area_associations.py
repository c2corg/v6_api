from dataclasses import dataclass

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import (
    AreaAssociation,
    get_areas,
    update_area,
    update_areas_for_document,
)
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    area1: Area
    area2: Area
    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    waypoint4: Waypoint
    waypoint5: Waypoint


@pytest.fixture
def docs(session) -> Docs:
    area1 = Area(
        area_type='range',
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
        ),
    )
    session.add(area1)
    session.flush()
    area2 = Area(
        area_type='range',
        redirects_to=area1.document_id,
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
        ),
    )

    # wp inside the area
    waypoint1 = Waypoint(
        waypoint_type='summit',
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
        ),
    )
    # wp outside the area
    waypoint2 = Waypoint(
        waypoint_type='summit',
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(693666.031687976 5741108.7574713)'
        ),
    )
    # wp without geometry
    waypoint3 = Waypoint(waypoint_type='summit')
    # wp with empty geometry
    waypoint4 = Waypoint(waypoint_type='summit', geometry=DocumentGeometry())
    session.add_all([area2, waypoint1, waypoint2, waypoint3, waypoint4])
    session.flush()

    # wp inside the area, but with `redirects_to` (should be ignored)
    waypoint5 = Waypoint(
        waypoint_type='summit',
        redirects_to=waypoint1.document_id,
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
        ),
    )
    session.add(waypoint5)
    return Docs(
        area1=area1,
        area2=area2,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        waypoint4=waypoint4,
        waypoint5=waypoint5,
    )


def test_update_area(session, docs):
    update_area(docs.area1)

    added_links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area1.document_id)
        .all()
    )
    assert len(added_links) == 1
    assert added_links[0].document_id == docs.waypoint1.document_id


def test_update_area_reset_first(session, docs):
    # add an association with wp2, which should be removed after the update
    session.add(
        AreaAssociation(
            document_id=docs.waypoint2.document_id, area_id=docs.area1.document_id
        )
    )
    session.flush()

    update_area(docs.area1, reset=True)

    updated_links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area1.document_id)
        .all()
    )
    assert len(updated_links) == 1
    assert updated_links[0].document_id == docs.waypoint1.document_id


def test_update_area_reset_first_forwarded(session, docs):
    """Tests that areas with `redirects_to` are ignored."""
    # add an association with wp2, which should be removed after the update
    session.add(
        AreaAssociation(
            document_id=docs.waypoint2.document_id, area_id=docs.area2.document_id
        )
    )
    session.flush()

    update_area(docs.area2, reset=True)

    updated_links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area2.document_id)
        .all()
    )
    assert len(updated_links) == 0


def test_update_document(session, docs):
    # waypoint inside the area
    update_areas_for_document(docs.waypoint1)

    added_links = _get_links_for_document(session, docs.waypoint1)
    assert len(added_links) == 1
    assert added_links[0].area_id == docs.area1.document_id

    # wp outside the area
    update_areas_for_document(docs.waypoint2)

    added_links = _get_links_for_document(session, docs.waypoint2)
    assert len(added_links) == 0

    # wp without geometry
    update_areas_for_document(docs.waypoint3)

    added_links = _get_links_for_document(session, docs.waypoint3)
    assert len(added_links) == 0

    # wp with empty geometry
    update_areas_for_document(docs.waypoint4)

    added_links = _get_links_for_document(session, docs.waypoint4)
    assert len(added_links) == 0


def test_update_document_forwarded(session, docs):
    # waypoint inside the area but forwarded (should be ignored)
    update_areas_for_document(docs.waypoint5)

    added_links = _get_links_for_document(session, docs.waypoint1)
    assert len(added_links) == 0


def test_update_document_reset_first(session, docs):
    # add an association with wp2, which should be removed after the update
    session.add(
        AreaAssociation(
            document_id=docs.waypoint2.document_id, area_id=docs.area1.document_id
        )
    )
    session.flush()

    update_areas_for_document(docs.waypoint2, reset=True)

    updated_links = _get_links_for_document(session, docs.waypoint2)
    assert len(updated_links) == 0


def test_get_areas(docs):
    update_area(docs.area1)
    areas = get_areas(docs.waypoint1, 'en')

    assert len(areas) == 1
    assert areas[0].document_id == docs.area1.document_id


def test_get_areas_forwarded(session, docs):
    """Tests that forwarded areas are not included."""
    # add an association with wp1
    session.add(
        AreaAssociation(
            document_id=docs.waypoint1.document_id, area_id=docs.area2.document_id
        )
    )
    session.flush()
    areas = get_areas(docs.waypoint1, 'en')

    assert len(areas) == 0


def _get_links_for_document(session, doc):
    return (
        session.query(AreaAssociation)
        .filter(AreaAssociation.document_id == doc.document_id)
        .all()
    )
