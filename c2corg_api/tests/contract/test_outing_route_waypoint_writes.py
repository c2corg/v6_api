from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import WriteContractTest, writable


def error_names(response):
    return sorted(e['name'] for e in response.json['errors'])


class OutingRouteWaypointTest(WriteContractTest):
    def creation(self, prefix):
        """Return a creation body copied from the document of setUp."""
        document = writable(self.get(self.url(prefix)).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        return document


class TestOutingWrites(OutingRouteWaypointTest):
    @contract(('PUT', '/outings/{id}'))
    def test_update_by_another_user(self):
        # only its associated users and the moderators
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = self.update('outings', change, user='contributor2', status=403)
        check_snapshot('outings_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this outing'
        )

    @contract(('POST', '/outings'))
    def test_create_without_route_and_user(self):
        document = self.creation('outings')
        document['associations'] = {}
        response = self.post('/outings', document, user='contributor', status=400)
        check_snapshot('outings_create_no_associations', response)
        assert error_names(response) == ['associations.routes', 'associations.users']

    @contract(('POST', '/outings'))
    def test_create_with_dates_in_the_wrong_order(self):
        document = self.creation('outings')
        document['associations'] = {
            'routes': [{'document_id': self.ids['routes']}],
            'users': [{'document_id': self.global_userids['contributor']}],
        }
        document.update(date_start='2016-01-02', date_end='2016-01-01')
        response = self.post('/outings', document, user='contributor', status=400)
        check_snapshot('outings_create_dates', response)
        assert error_names(response) == ['date_end']


class TestRouteWrites(OutingRouteWaypointTest):
    @contract(('POST', '/routes'))
    def test_create_without_waypoint(self):
        document = self.creation('routes')
        document.pop('main_waypoint_id', None)
        document['associations'] = {}
        response = self.post('/routes', document, user='contributor', status=400)
        check_snapshot('routes_create_no_waypoint', response)
        assert error_names(response) == ['associations.waypoints']

    @contract(('POST', '/routes'))
    def test_create_with_a_main_waypoint_not_associated(self):
        document = self.creation('routes')
        document['associations'] = {
            'waypoints': [{'document_id': self.ids['waypoints']}]
        }
        document['main_waypoint_id'] = self.ids['articles']
        response = self.post('/routes', document, user='contributor', status=400)
        check_snapshot('routes_create_main_waypoint', response)
        assert error_names(response) == ['main_waypoint_id']


class TestWaypointWrites(OutingRouteWaypointTest):
    @contract(('POST', '/waypoints'))
    def test_create_invalid(self):
        document = self.creation('waypoints')
        document['waypoint_type'] = 'no such type'
        response = self.post('/waypoints', document, user='contributor', status=400)
        check_snapshot('waypoints_create_invalid', response)
        assert error_names(response) == ['waypoint_type']
