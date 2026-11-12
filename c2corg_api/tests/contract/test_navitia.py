import json
import os
from unittest.mock import Mock, patch

import pytest

from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_misc import POLYGON_4326
from c2corg_api.views.navitia import JOB_TTL, redis_client

JOURNEYS = ('GET', '/navitia/journeys')
ISOCHRONE_ROUTES = ('GET', '/navitia/isochronesreachableroutes')
ISOCHRONE_WAYPOINTS = ('GET', '/navitia/isochronesreachablewaypoints')
JOBS = [
    (kind, path.format(kind=kind))
    for kind in ('routes', 'waypoints')
    for path in (
        '/navitia/journeyreachable{kind}/start',
        '/navitia/journeyreachable{kind}/result/{{job_id}}',
        '/navitia/journeyreachable{kind}/progress/{{job_id}}',
    )
]
START = [('GET', path) for _, path in JOBS if path.endswith('/start')]
RESULT = [('GET', path) for _, path in JOBS if '/result/' in path]
PROGRESS = [('GET', path) for _, path in JOBS if '/progress/' in path]

JOURNEY_PARAMS = {
    'from': '5.73;45.18',
    'to': '5.92;45.57',
    'datetime': '20260116T115100',
    'datetime_represents': 'departure',
}
ISOCHRONE_PARAMS = {
    # in the coverage of the documents fixture, which the isochrone needs
    'from': '5.71;45.655',
    'datetime': '20260116T115100',
    'datetime_represents': 'departure',
    'boundary_duration': '3600',
}
JOB_PARAMS = {
    'from': '5.73;45.18',
    'datetime': '20260116T115100',
    'datetime_represents': 'departure',
    'walking_speed': '1.12',
    'max_walking_duration_to_pt': '1800',
}


def navitia_answer(status, body):
    """Return a fake answer of the Navitia API."""
    response = Mock(status_code=status, ok=200 <= status < 300)
    response.json.return_value = body
    return response


pytestmark = pytest.mark.usefixtures('stoparea_link')


@pytest.fixture(autouse=True)
def navitia_key(monkeypatch):
    """Set the key of the Navitia API, whose answers the tests fake."""
    monkeypatch.setenv('NAVITIA_API_KEY', 'contract-test-key')


def fake_navitia(status, body):
    """Fake the answer of the Navitia API."""
    return patch(
        'c2corg_api.views.navitia.requests.get',
        return_value=navitia_answer(status, body),
    )


class _Jobs:
    """The values of Navitia jobs in Redis, deleted after the test."""

    def __init__(self):
        self.redis = redis_client()
        self.keys = []

    def store(self, job_id, **values):
        for name, value in values.items():
            self.redis.set(f'job:{job_id}:{name}', value, ex=JOB_TTL)
        self.forget(*(f'job:{job_id}:{name}' for name in values))

    def forget(self, *keys):
        """Delete these keys after the test."""
        self.keys.extend(keys)


@pytest.fixture
def jobs():
    """Store Navitia job values in Redis; delete them after the test."""
    jobs = _Jobs()
    yield jobs
    if jobs.keys:
        jobs.redis.delete(*jobs.keys)


class TestJourneys:
    @contract(JOURNEYS)
    def test_journeys(self, browser):
        with fake_navitia(200, {'journeys': [{'duration': 3600}]}) as get:
            response = browser.get('/navitia/journeys', params=JOURNEY_PARAMS)
        check_snapshot('navitia_journeys', response)
        assert response.json == {'journeys': [{'duration': 3600}]}
        assert get.call_args.kwargs['headers'] == {'Authorization': 'contract-test-key'}

    @contract(JOURNEYS)
    def test_missing_parameters(self, browser):
        response = browser.get(
            '/navitia/journeys',
            params={'from': '5.73;45.18'},
            status=422,
        )
        check_snapshot('navitia_journeys_missing', response)
        assert [name for _, name, _ in invalid_parameters(response)] == [
            'to',
            'datetime',
            'datetime_represents',
        ]

    @contract(JOURNEYS)
    def test_no_solution(self, browser):
        with fake_navitia(404, {'error': {'id': 'no_solution'}}):
            response = browser.get(
                '/navitia/journeys', params=JOURNEY_PARAMS, status=404
            )
        check_snapshot('navitia_journeys_no_solution', response)
        assert response.json['errors'][0]['description'] == 'no_solution'

    @contract(JOURNEYS)
    def test_missing_key(self, browser):
        with patch.dict(os.environ, {'NAVITIA_API_KEY': ''}):
            response = browser.get(
                '/navitia/journeys', params=JOURNEY_PARAMS, status=500
            )
        check_snapshot('navitia_journeys_no_key', response)
        assert response.json['errors'][0]['description'] == (
            'Navitia API config is missing'
        )


@pytest.fixture
def navitia_coverage(browser):
    """Add the coverage the isochrone needs, in longitude and latitude."""
    # the isochrone needs the coverage of its source: in production the
    # polygons of the coverages are in longitude and latitude
    browser.create(
        'coverages',
        {
            'coverage_type': 'fr-se',
            'geometry': {'geom_detail': POLYGON_4326},
            'locales': [{'lang': 'en', 'title': 'Navitia coverage'}],
        },
    )


@pytest.mark.usefixtures('navitia_coverage')
class TestIsochrones:
    @contract(ISOCHRONE_ROUTES, ISOCHRONE_WAYPOINTS)
    def test_isochrone(self, browser):
        # an isochrone far from the stop area: no document inside it
        geojson = {
            'type': 'MultiPolygon',
            'coordinates': [[[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]],
        }
        for kind in ('routes', 'waypoints'):
            with fake_navitia(200, {'isochrones': [{'geojson': geojson}]}):
                response = browser.get(
                    f'/navitia/isochronesreachable{kind}',
                    params=ISOCHRONE_PARAMS,
                )
            check_snapshot(f'navitia_isochrone_{kind}', response)
            assert response.json == {
                'documents': [],
                'total': 0,
                'isochron_geom': geojson,
            }

    @contract(ISOCHRONE_ROUTES, ISOCHRONE_WAYPOINTS)
    def test_errors(self, browser):
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/isochronesreachable{kind}'
            response = browser.get(url, params={'from': '5.73;45.18'}, status=422)
            check_snapshot('navitia_isochrone_missing', response)
            with fake_navitia(404, {'error': {'id': 'no_solution'}}):
                response = browser.get(url, params=ISOCHRONE_PARAMS, status=404)
            check_snapshot('navitia_isochrone_no_solution', response)
            assert response.json['errors'][0]['description'] == 'no_solution'


class TestJobs:
    @contract(*START)
    def test_start(self, browser, jobs):
        for kind in ('routes', 'waypoints'):
            # the job itself runs in a thread: not here
            with patch(f'c2corg_api.views.navitia.compute_journey_reachable_{kind}'):
                response = browser.get(
                    f'/navitia/journeyreachable{kind}/start',
                    params=JOB_PARAMS,
                )
            check_snapshot('navitia_job_start', response)
            job_id = response.json['job_id']
            jobs.forget(f'job:{job_id}:progress', f'job:{job_id}:status')
            assert jobs.redis.get(f'job:{job_id}:status') == b'running'

    @contract(*START)
    def test_start_missing_parameters(self, browser):
        for kind in ('routes', 'waypoints'):
            response = browser.get(
                f'/navitia/journeyreachable{kind}/start',
                params={'from': '5.73;45.18'},
                status=422,
            )
            check_snapshot('navitia_job_start_missing', response)
            assert len(response.json['detail']) == 4

    @contract(*RESULT)
    def test_result(self, browser, jobs):
        result = {'documents': [], 'total': 0}
        jobs.store('done-job', status='done', result=json.dumps(result))
        jobs.store(
            'failed-job',
            status='error',
            error=json.dumps({'id': 'no_solution', 'message': 'no_solution'}),
        )
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/journeyreachable{kind}/result/'
            done = browser.get(url + 'done-job')
            check_snapshot('navitia_job_result_done', done)
            assert done.json == {'status': 'done', 'result': result}
            failed = browser.get(url + 'failed-job')
            check_snapshot('navitia_job_result_error', failed)
            assert failed.json == {'status': 'error', 'message': 'no_solution'}
            unknown = browser.get(url + 'no-such-job')
            check_snapshot('navitia_job_result_unknown', unknown)
            assert unknown.json == {'error': 'unknown_job_id'}

    @contract(*PROGRESS)
    def test_progress(self, browser, jobs):
        jobs.store(
            'done-job', status='done', progress='3', found='2', not_found='1', total='3'
        )
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/journeyreachable{kind}/progress/'
            done = browser.get(url + 'done-job')
            check_snapshot('navitia_job_progress_done', done)
            assert done.text == (
                'data: {"progress": 3, "total": 3, "found": 2, "not_found": 1}\n\n'
                'event: done\ndata: done\n\n'
            )
            unknown = browser.get(url + 'no-such-job')
            check_snapshot('navitia_job_progress_unknown', unknown)
            assert unknown.text == (
                'event: error\n'
                'data: {"id": "unknown_job", "message": "Unknown job no-such-job"}\n\n'
            )
