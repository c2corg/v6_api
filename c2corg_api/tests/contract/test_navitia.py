import json
import os
from unittest.mock import Mock, patch

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_misc import POLYGON_4326
from c2corg_api.tests.contract.test_stopareas import StopareaContractTest
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
    # in the coverage of DocumentContractTest, which the isochrone needs
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


class NavitiaContractTest(StopareaContractTest):
    """The Navitia API is faked: its key is set, its answers are given."""

    def setUp(self):
        super().setUp()
        self.cleanups = []
        key = patch.dict(os.environ, {'NAVITIA_API_KEY': 'contract-test-key'})
        key.start()
        self.addCleanup(key.stop)

    def addCleanup(self, function, *args):  # noqa: N802 (as unittest)
        self.cleanups.append((function, args))

    def tearDown(self):
        for function, args in reversed(self.cleanups):
            function(*args)
        super().tearDown()

    def navitia(self, status, body):
        return patch(
            'c2corg_api.views.navitia.requests.get',
            return_value=navitia_answer(status, body),
        )


class TestJourneys(NavitiaContractTest):
    @contract(JOURNEYS)
    def test_journeys(self):
        with self.navitia(200, {'journeys': [{'duration': 3600}]}) as get:
            response = self.get('/navitia/journeys', params=JOURNEY_PARAMS)
        check_snapshot('navitia_journeys', response)
        assert response.json == {'journeys': [{'duration': 3600}]}
        assert get.call_args.kwargs['headers'] == {'Authorization': 'contract-test-key'}

    @contract(JOURNEYS)
    def test_missing_parameters(self):
        response = self.get(
            '/navitia/journeys', params={'from': '5.73;45.18'}, status=400
        )
        check_snapshot('navitia_journeys_missing', response)
        assert [e['name'] for e in response.json['errors']] == [
            'to',
            'datetime',
            'datetime_represents',
        ]

    @contract(JOURNEYS)
    def test_no_solution(self):
        with self.navitia(404, {'error': {'id': 'no_solution'}}):
            response = self.get('/navitia/journeys', params=JOURNEY_PARAMS, status=404)
        check_snapshot('navitia_journeys_no_solution', response)
        assert response.json['errors'][0]['description'] == 'no_solution'

    @contract(JOURNEYS)
    def test_missing_key(self):
        with patch.dict(os.environ, {'NAVITIA_API_KEY': ''}):
            response = self.get('/navitia/journeys', params=JOURNEY_PARAMS, status=500)
        check_snapshot('navitia_journeys_no_key', response)
        assert response.json['errors'][0]['description'] == (
            'Navitia API config is missing'
        )


class TestIsochrones(NavitiaContractTest):
    def setUp(self):
        super().setUp()
        # the isochrone needs the coverage of its source: in production the
        # polygons of the coverages are in longitude and latitude
        self.create(
            'coverages',
            {
                'coverage_type': 'fr-se',
                'geometry': {'geom_detail': POLYGON_4326},
                'locales': [{'lang': 'en', 'title': 'Navitia coverage'}],
            },
        )

    @contract(ISOCHRONE_ROUTES, ISOCHRONE_WAYPOINTS)
    def test_isochrone(self):
        # an isochrone far from the stop area: no document inside it
        geojson = {
            'type': 'MultiPolygon',
            'coordinates': [[[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]],
        }
        for kind in ('routes', 'waypoints'):
            with self.navitia(200, {'isochrones': [{'geojson': geojson}]}):
                response = self.get(
                    f'/navitia/isochronesreachable{kind}', params=ISOCHRONE_PARAMS
                )
            check_snapshot(f'navitia_isochrone_{kind}', response)
            assert response.json == {
                'documents': [],
                'total': 0,
                'isochron_geom': geojson,
            }

    @contract(ISOCHRONE_ROUTES, ISOCHRONE_WAYPOINTS)
    def test_errors(self):
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/isochronesreachable{kind}'
            response = self.get(url, params={'from': '5.73;45.18'}, status=400)
            check_snapshot('navitia_isochrone_missing', response)
            with self.navitia(404, {'error': {'id': 'no_solution'}}):
                response = self.get(url, params=ISOCHRONE_PARAMS, status=404)
            check_snapshot('navitia_isochrone_no_solution', response)
            assert response.json['errors'][0]['description'] == 'no_solution'


class TestJobs(NavitiaContractTest):
    def setUp(self):
        super().setUp()
        self.redis = redis_client()

    def store_job(self, job_id, **values):
        for name, value in values.items():
            self.redis.set(f'job:{job_id}:{name}', value, ex=JOB_TTL)
        self.addCleanup(self.redis.delete, *(f'job:{job_id}:{name}' for name in values))

    @contract(*START)
    def test_start(self):
        for kind in ('routes', 'waypoints'):
            # the job itself runs in a thread: not here
            with patch(f'c2corg_api.views.navitia.compute_journey_reachable_{kind}'):
                response = self.get(
                    f'/navitia/journeyreachable{kind}/start', params=JOB_PARAMS
                )
            check_snapshot('navitia_job_start', response)
            job_id = response.json['job_id']
            self.addCleanup(
                self.redis.delete, f'job:{job_id}:progress', f'job:{job_id}:status'
            )
            assert self.redis.get(f'job:{job_id}:status') == b'running'

    @contract(*START)
    def test_start_missing_parameters(self):
        for kind in ('routes', 'waypoints'):
            response = self.get(
                f'/navitia/journeyreachable{kind}/start',
                params={'from': '5.73;45.18'},
                status=400,
            )
            check_snapshot('navitia_job_start_missing', response)
            assert len(response.json['errors']) == 4

    @contract(*RESULT)
    def test_result(self):
        result = {'documents': [], 'total': 0}
        self.store_job('done-job', status='done', result=json.dumps(result))
        self.store_job(
            'failed-job',
            status='error',
            error=json.dumps({'id': 'no_solution', 'message': 'no_solution'}),
        )
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/journeyreachable{kind}/result/'
            done = self.get(url + 'done-job')
            check_snapshot('navitia_job_result_done', done)
            assert done.json == {'status': 'done', 'result': result}
            failed = self.get(url + 'failed-job')
            check_snapshot('navitia_job_result_error', failed)
            assert failed.json == {'status': 'error', 'message': 'no_solution'}
            unknown = self.get(url + 'no-such-job')
            check_snapshot('navitia_job_result_unknown', unknown)
            assert unknown.json == {'error': 'unknown_job_id'}

    @contract(*PROGRESS)
    def test_progress(self):
        self.store_job(
            'done-job', status='done', progress='3', found='2', not_found='1', total='3'
        )
        for kind in ('routes', 'waypoints'):
            url = f'/navitia/journeyreachable{kind}/progress/'
            done = self.get(url + 'done-job')
            check_snapshot('navitia_job_progress_done', done)
            assert done.text == (
                'data: {"progress": 3, "total": 3, "found": 2, "not_found": 1}\n\n'
                'event: done\ndata: done\n\n'
            )
            unknown = self.get(url + 'no-such-job')
            check_snapshot('navitia_job_progress_unknown', unknown)
            assert unknown.text == (
                'event: error\n'
                'data: {"id": "unknown_job", "message": "Unknown job no-such-job"}\n\n'
            )
