import pytest

from c2corg_api.tests import errors_of
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import writable


def error_names(response):
    return sorted(e['name'] for e in errors_of(response.json))


def creation(documents, prefix):
    """Return a creation body copied from the document of the fixture."""
    document = writable(
        documents.browser.get(documents.url(prefix)).json, keep_ids=False
    )
    for locale in document['locales']:
        locale.pop('version', None)
    return document


@pytest.mark.usefixtures('documents')
class TestOutingWrites:
    @contract(('PUT', '/outings/{id}'))
    def test_update_by_another_user(self, documents):
        # only its associated users and the moderators
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = documents.update(
            'outings',
            change,
            user='contributor2',
            status=403,
        )
        check_snapshot('outings_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this outing'
        )

    @contract(('POST', '/outings'))
    def test_create_without_route_and_user(self, browser, documents):
        document = creation(documents, 'outings')
        document['associations'] = {}
        response = browser.post('/outings', document, user='contributor', status=400)
        check_snapshot('outings_create_no_associations', response)
        assert error_names(response) == ['associations.routes', 'associations.users']

    @contract(('POST', '/outings'))
    def test_create_with_dates_in_the_wrong_order(self, user_ids, browser, documents):
        document = creation(documents, 'outings')
        document['associations'] = {
            'routes': [{'document_id': documents.ids['routes']}],
            'users': [{'document_id': user_ids['contributor']}],
        }
        document.update(date_start='2016-01-02', date_end='2016-01-01')
        response = browser.post('/outings', document, user='contributor', status=400)
        check_snapshot('outings_create_dates', response)
        assert error_names(response) == ['date_end']


@pytest.mark.usefixtures('documents')
class TestRouteWrites:
    @contract(('POST', '/routes'))
    def test_create_without_waypoint(self, browser, documents):
        document = creation(documents, 'routes')
        document.pop('main_waypoint_id', None)
        document['associations'] = {}
        response = browser.post('/routes', document, user='contributor', status=400)
        check_snapshot('routes_create_no_waypoint', response)
        assert error_names(response) == ['associations.waypoints']

    @contract(('POST', '/routes'))
    def test_create_with_a_main_waypoint_not_associated(self, browser, documents):
        document = creation(documents, 'routes')
        document['associations'] = {
            'waypoints': [{'document_id': documents.ids['waypoints']}]
        }
        document['main_waypoint_id'] = documents.ids['articles']
        response = browser.post('/routes', document, user='contributor', status=400)
        check_snapshot('routes_create_main_waypoint', response)
        assert error_names(response) == ['main_waypoint_id']


@pytest.mark.usefixtures('documents')
class TestWaypointWrites:
    @contract(('POST', '/waypoints'))
    def test_create_invalid(self, browser, documents):
        document = creation(documents, 'waypoints')
        document['waypoint_type'] = 'no such type'
        response = browser.post('/waypoints', document, user='contributor', status=422)
        check_snapshot('waypoints_create_invalid', response)
        assert error_names(response) == ['waypoint_type']
