from unittest.mock import patch

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.views import BaseTestRest

POINT = 'SRID=3857;POINT(635961 5723624)'


class TestReachable(BaseTestRest):
    """A route whose access waypoint has a stop area, both in an area."""

    def setUp(self):
        super().setUp()
        area = Area(area_type='range', locales=[DocumentLocale(lang='fr', title='A')])
        access = Waypoint(
            waypoint_type='access',
            elevation=900,
            geometry=DocumentGeometry(geom=POINT),
            locales=[DocumentLocale(lang='fr', title='Arret')],
        )
        route = Route(
            activities=['hiking'],
            geometry=DocumentGeometry(geom=POINT),
            locales=[RouteLocale(lang='fr', title='Boucle')],
        )
        self.session.add_all([area, access, route])
        self.session.flush()
        stoparea = Stoparea(
            navitia_id='stop_area:1',
            stoparea_name='Arret',
            line='1',
            operator='Bus',
            geom=POINT,
        )
        self.session.add(stoparea)
        self.session.flush()
        self.session.add_all(
            [
                Association(
                    parent_document_id=access.document_id,
                    parent_document_type=WAYPOINT_TYPE,
                    child_document_id=route.document_id,
                    child_document_type=ROUTE_TYPE,
                ),
                AreaAssociation(
                    document_id=route.document_id, area_id=area.document_id
                ),
                AreaAssociation(
                    document_id=access.document_id, area_id=area.document_id
                ),
                WaypointStoparea(
                    waypoint_id=access.document_id,
                    stoparea_id=stoparea.stoparea_id,
                    distance=10,
                ),
            ]
        )
        self.session.flush()
        self.route_id = route.document_id
        self.access_id = access.document_id
        self.area_id = area.document_id

    def get_reachable(self, path, module, doc_id):
        # the ids filtered by ElasticSearch: the document only
        with patch(
            f'c2corg_api.views.{module}.get_all_filtered_docs',
            return_value=([doc_id], 1),
        ):
            return self.app.get(path, status=200).json

    def test_reachable_routes(self):
        body = self.get_reachable('/reachableroutes', 'route', self.route_id)
        assert [d['document_id'] for d in body['documents']] == [self.route_id]
        areas = body['documents'][0]['areas']
        assert [a['document_id'] for a in areas] == [self.area_id]

    def test_reachable_waypoints(self):
        body = self.get_reachable('/reachablewaypoints', 'waypoint', self.access_id)
        assert [d['document_id'] for d in body['documents']] == [self.access_id]
        areas = body['documents'][0]['areas']
        assert [a['document_id'] for a in areas] == [self.area_id]
