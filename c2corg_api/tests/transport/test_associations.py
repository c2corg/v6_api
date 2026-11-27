import datetime

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.transport.associations import get_linked_documents


class TestLinkedDocuments:
    @pytest.fixture(autouse=True)
    def documents(self, session):
        self.session = session
        self._add_test_data()

    def _add_waypoint(self, title_fr, title_en):
        waypoint = Waypoint(waypoint_type='summit', elevation=2000)
        waypoint.locales.append(WaypointLocale(lang='fr', title=title_fr))
        waypoint.locales.append(WaypointLocale(lang='en', title=title_en))
        self.session.add(waypoint)
        self.session.flush()
        return waypoint

    def _add_route(self, title):
        route = Route(activities=['hiking'], elevation_max=2000)
        route.locales.append(RouteLocale(lang='fr', title=title))
        self.session.add(route)
        self.session.flush()
        return route

    def _add_outing(self, title, day):
        outing = Outing(activities=['hiking'], date_start=day, date_end=day)
        outing.locales.append(OutingLocale(lang='fr', title=title))
        self.session.add(outing)
        self.session.flush()
        return outing

    def _add_stop(self, stoparea_id, navitia_id, waypoint, distance):
        self.session.add(
            Stoparea(
                stoparea_id=stoparea_id,
                navitia_id=navitia_id,
                stoparea_name='Stop ' + navitia_id,
                line='A',
                operator='Operator',
            )
        )
        self.session.flush()
        self.session.add(
            WaypointStoparea(
                waypoint_id=waypoint.document_id,
                stoparea_id=stoparea_id,
                distance=distance,
            )
        )
        self.session.flush()

    def _associate(self, parent, child):
        self.session.add(Association.create(parent, child))
        self.session.flush()

    def _add_test_data(self):
        self.near = self._add_waypoint('Parking proche', 'Near parking')
        self.far = self._add_waypoint('Parking loin', 'Far parking')
        self.alone = self._add_waypoint('Sans arret', 'No stop')

        self._add_stop(9001, 'stop_area:A', self.near, 0.4)
        self._add_stop(9002, 'stop_area:B', self.near, 0.9)
        self._add_stop(9003, 'stop_area:B', self.far, 2.5)
        self._add_stop(9004, 'stop_area:C', self.alone, 1.0)

        self.popular = self._add_route('Voie populaire')
        self.quiet = self._add_route('Voie calme')
        self.unrelated = self._add_route('Voie ailleurs')
        self._associate(self.near, self.popular)
        self._associate(self.far, self.quiet)
        self._associate(self.alone, self.unrelated)

        self.old = self._add_outing('Sortie ancienne', datetime.date(2020, 1, 1))
        self.recent = self._add_outing('Sortie recente', datetime.date(2026, 1, 1))
        self.other = self._add_outing('Autre sortie', datetime.date(2025, 1, 1))
        self._associate(self.popular, self.old)
        self._associate(self.popular, self.recent)
        self._associate(self.quiet, self.other)

    def test_nothing_without_stop_areas(self):
        empty = {'waypoints': [], 'waypoint_ids': [], 'routes': [], 'outings': []}

        assert get_linked_documents(self.session, [], 'fr') == empty
        assert get_linked_documents(self.session, ['stop_area:unknown'], 'fr') == empty

    def test_documents_reached_from_a_stop_area(self):
        linked = get_linked_documents(self.session, ['stop_area:A'], 'fr')

        assert [w['document_id'] for w in linked['waypoints']] == [
            self.near.document_id
        ]
        assert linked['waypoint_ids'] == [self.near.document_id]
        assert linked['waypoints'][0]['title'] == 'Parking proche'
        assert linked['waypoints'][0]['distance'] == 0.4
        assert [r['document_id'] for r in linked['routes']] == [
            self.popular.document_id
        ]
        # the most recent outing first
        assert [o['document_id'] for o in linked['outings']] == [
            self.recent.document_id,
            self.old.document_id,
        ]
        assert linked['outings'][0]['date_end'] == '2026-01-01'

    def test_a_stop_area_near_several_waypoints_gives_the_nearest_first(self):
        linked = get_linked_documents(self.session, ['stop_area:B'], 'fr')

        assert [w['document_id'] for w in linked['waypoints']] == [
            self.near.document_id,
            self.far.document_id,
        ]
        assert linked['waypoint_ids'] == [self.near.document_id, self.far.document_id]
        assert {r['document_id'] for r in linked['routes']} == {
            self.popular.document_id,
            self.quiet.document_id,
        }
        # the route with the most outings comes first
        assert linked['routes'][0]['document_id'] == self.popular.document_id

    def test_several_stop_areas_are_looked_at_together(self):
        linked = get_linked_documents(
            self.session, ['stop_area:A', 'stop_area:C'], 'fr'
        )

        assert {w['document_id'] for w in linked['waypoints']} == {
            self.near.document_id,
            self.alone.document_id,
        }

    def test_titles_in_the_requested_language_else_any(self):
        english = get_linked_documents(self.session, ['stop_area:A'], 'en')
        german = get_linked_documents(self.session, ['stop_area:A'], 'de')

        assert english['waypoints'][0]['title'] == 'Near parking'
        # no English title for the route: the one it has
        assert english['routes'][0]['title'] == 'Voie populaire'
        assert german['waypoints'][0]['title'] in ('Parking proche', 'Near parking')

    def test_the_number_of_documents_is_limited(self):
        linked = get_linked_documents(self.session, ['stop_area:B'], 'fr', limit=1)

        assert len(linked['waypoints']) == 1
        # the filters of the lists of routes and outings need all of them
        assert len(linked['waypoint_ids']) == 2
        assert len(linked['routes']) == 1
        assert len(linked['outings']) == 1
