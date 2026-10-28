import threading
from unittest import mock

from sqlalchemy import text

from c2corg_api.models import DBSession
from c2corg_api.tests import BaseTestCase, get_engine
from c2corg_api.views.navitia import (
    JOB_TTL,
    compute_journey_reachable_routes,
    compute_journey_reachable_waypoints,
)

NAVITIA = 'c2corg_api.views.navitia.'


def _query_using_db(fail=False):
    """Return a fake query whose `all()` really uses `DBSession`."""

    def all_():
        DBSession.execute(text('SELECT 1'))
        if fail:
            raise RuntimeError('query failed')
        return []

    query = mock.Mock()
    query.all.side_effect = all_
    return query, 0


class TestNavitiaJobDbSession(BaseTestCase):
    """Background jobs must give their connection back to the pool."""

    # The jobs run in their own thread, outside of pyramid_tm: they must end
    # their transaction and remove their scoped session themselves.

    def setUp(self):
        super().setUp()
        # Use a real pool (not the test connection) to count connections.
        self.job_engine = get_engine()
        DBSession.configure(bind=self.job_engine)

    def tearDown(self):
        DBSession.configure(bind=self.connection)
        self.job_engine.dispose()
        super().tearDown()

    def _run_in_thread(self, job, request):
        state = {}

        def target():
            job('job-123', request)
            state['session_left'] = DBSession.registry.has()

        with (
            mock.patch(NAVITIA + 'redis_client') as redis_client,
            mock.patch(NAVITIA + 'extract_meta_params'),
            mock.patch(NAVITIA + 'extract_journey_params'),
        ):
            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout=30)
            assert not thread.is_alive()
        return state, redis_client.return_value

    def _assert_connection_released(self, state):
        pool = self.job_engine.pool
        # the job did use a connection ...
        assert pool.checkedin() == 1
        # ... and gave it back to the pool
        assert pool.checkedout() == 0
        assert not state['session_left']

    def test_waypoints_job_releases_connection(self):
        request = mock.Mock()
        request.GET = {'a': '1'}
        with mock.patch(
            NAVITIA + 'build_reachable_waypoints_query', return_value=_query_using_db()
        ):
            state, r = self._run_in_thread(compute_journey_reachable_waypoints, request)

        r.set.assert_any_call('job:job-123:status', 'done', ex=JOB_TTL)
        self._assert_connection_released(state)

    def test_routes_job_releases_connection_on_error(self):
        request = mock.Mock()
        request.GET = {}
        with mock.patch(
            NAVITIA + 'build_reachable_route_query_with_waypoints',
            return_value=_query_using_db(fail=True),
        ):
            state, r = self._run_in_thread(compute_journey_reachable_routes, request)

        r.set.assert_any_call('job:job-123:status', 'error', ex=JOB_TTL)
        self._assert_connection_released(state)
