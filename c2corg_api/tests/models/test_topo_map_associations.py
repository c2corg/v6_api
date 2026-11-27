from dataclasses import dataclass

import pytest

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import (
    TopoMapAssociation,
    get_maps,
    update_map,
    update_maps_for_document,
)
from c2corg_api.models.waypoint import Waypoint


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    map1: TopoMap
    map2: TopoMap
    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    waypoint4: Waypoint
    waypoint5: Waypoint


@pytest.fixture
def docs(session) -> Docs:
    map1 = TopoMap(
        code='3232ET',
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
        ),
    )
    session.add(map1)
    session.flush()
    map2 = TopoMap(
        code='3233ET',
        redirects_to=map1.document_id,
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
        ),
    )

    # wp inside the area of the map
    waypoint1 = Waypoint(
        waypoint_type='summit',
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
        ),
    )
    # wp outside the area of the map
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
    session.add_all([map2, waypoint1, waypoint2, waypoint3, waypoint4])
    session.flush()

    # wp inside the area of the map, but with `redirects_to`
    # (should be ignored)
    waypoint5 = Waypoint(
        waypoint_type='summit',
        redirects_to=waypoint1.document_id,
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
        ),
    )
    session.add(waypoint5)
    return Docs(
        map1=map1,
        map2=map2,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        waypoint4=waypoint4,
        waypoint5=waypoint5,
    )


def test_update_map(session, docs):
    update_map(docs.map1)

    added_links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.topo_map_id == docs.map1.document_id)
        .all()
    )
    assert len(added_links) == 1
    assert added_links[0].document_id == docs.waypoint1.document_id


def test_update_map_reset_first(session, docs):
    # add an association with wp2, which should be removed after the update
    session.add(
        TopoMapAssociation(
            document_id=docs.waypoint2.document_id,
            topo_map_id=docs.map1.document_id,
        )
    )
    session.flush()

    update_map(docs.map1, reset=True)

    updated_links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.topo_map_id == docs.map1.document_id)
        .all()
    )
    assert len(updated_links) == 1
    assert updated_links[0].document_id == docs.waypoint1.document_id


def test_update_map_reset_first_forwarded(session, docs):
    """Tests that maps with `redirects_to` are ignored."""
    # add an association with wp2, which should be removed after the update
    session.add(
        TopoMapAssociation(
            document_id=docs.waypoint2.document_id,
            topo_map_id=docs.map2.document_id,
        )
    )
    session.flush()

    update_map(docs.map2, reset=True)

    updated_links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.topo_map_id == docs.map2.document_id)
        .all()
    )
    assert len(updated_links) == 0


def test_update_document(session, docs):
    # waypoint inside the area
    update_maps_for_document(docs.waypoint1)

    added_links = _get_links_for_document(session, docs.waypoint1)
    assert len(added_links) == 1
    assert added_links[0].topo_map_id == docs.map1.document_id

    # wp outside the area of the map
    update_maps_for_document(docs.waypoint2)

    added_links = _get_links_for_document(session, docs.waypoint2)
    assert len(added_links) == 0

    # wp without geometry
    update_maps_for_document(docs.waypoint3)

    added_links = _get_links_for_document(session, docs.waypoint3)
    assert len(added_links) == 0

    # wp with empty geometry
    update_maps_for_document(docs.waypoint4)

    added_links = _get_links_for_document(session, docs.waypoint4)
    assert len(added_links) == 0


def test_update_document_forwarded(session, docs):
    # waypoint inside the area of the map but forwarded (should be ignored)
    update_maps_for_document(docs.waypoint5)

    added_links = _get_links_for_document(session, docs.waypoint1)
    assert len(added_links) == 0


def test_update_document_reset_first(session, docs):
    # add an association with wp2, which should be removed after the update
    session.add(
        TopoMapAssociation(
            document_id=docs.waypoint2.document_id,
            topo_map_id=docs.map1.document_id,
        )
    )
    session.flush()

    update_maps_for_document(docs.waypoint2, reset=True)

    updated_links = _get_links_for_document(session, docs.waypoint2)
    assert len(updated_links) == 0


def test_get_maps(docs):
    update_map(docs.map1)
    maps = get_maps(docs.waypoint1, 'en')

    assert len(maps) == 1
    assert maps[0].document_id == docs.map1.document_id


def test_get_maps_forwarded(session, docs):
    """Tests that forwarded maps are not included."""
    # add an association with wp1
    session.add(
        TopoMapAssociation(
            document_id=docs.waypoint1.document_id,
            topo_map_id=docs.map2.document_id,
        )
    )
    session.flush()
    areas = get_maps(docs.waypoint1, 'en')

    assert len(areas) == 0


def _get_links_for_document(session, doc):
    return (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.document_id == doc.document_id)
        .all()
    )
