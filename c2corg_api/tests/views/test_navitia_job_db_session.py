import threading
from unittest import mock

import pytest
from sqlalchemy import text

from c2corg_api.models import DBSession
from c2corg_api.tests import get_engine
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


@pytest.fixture
def job_engine(db_connection):
    """Bind DBSession to an engine of its own, as in a Navitia job."""
    job_engine = get_engine()
    DBSession.configure(bind=job_engine)
    yield job_engine
    DBSession.configure(bind=db_connection)
    job_engine.dispose()


def _run_in_thread(job, request):
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


def _assert_connection_released(job_engine, state):
    pool = job_engine.pool
    # the job did use a connection ...
    assert pool.checkedin() == 1
    # ... and gave it back to the pool
    assert pool.checkedout() == 0
    assert not state['session_left']


def test_waypoints_job_releases_connection(job_engine):
    request = mock.Mock()
    request.GET = {'a': '1'}
    with mock.patch(
        NAVITIA + 'build_reachable_waypoints_query', return_value=_query_using_db()
    ):
        state, r = _run_in_thread(compute_journey_reachable_waypoints, request)

    r.set.assert_any_call('job:job-123:status', 'done', ex=JOB_TTL)
    _assert_connection_released(job_engine, state)


def test_routes_job_releases_connection_on_error(job_engine):
    request = mock.Mock()
    request.GET = {}
    with mock.patch(
        NAVITIA + 'build_reachable_route_query_with_waypoints',
        return_value=_query_using_db(fail=True),
    ):
        state, r = _run_in_thread(compute_journey_reachable_routes, request)

    r.set.assert_any_call('job:job-123:status', 'error', ex=JOB_TTL)
    _assert_connection_released(job_engine, state)
