import logging

import pytest

from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.search.notify_sync import run_on_successful_transaction


@pytest.fixture
def session(db_connection):
    # the session of the views, bound to the connection of the test
    yield DBSession()
    DBSession.remove()


class TestRunOnSuccessfulTransaction:
    def test_run_after_the_commit(self, session):
        calls = []
        run_on_successful_transaction(lambda: calls.append('run'))
        assert calls == []
        session.commit()
        assert calls == ['run']
        # once only
        session.commit()
        assert calls == ['run']

    def test_dropped_on_rollback(self, session, caplog):
        calls = []
        run_on_successful_transaction(lambda: calls.append('run'))
        with caplog.at_level(logging.WARNING):
            session.rollback()
        session.commit()
        assert calls == []
        assert 'not run because transaction was not successful' in caplog.text

    def test_failure_is_logged(self, session, caplog):
        def fail():
            raise RuntimeError('queue down')

        calls = []
        run_on_successful_transaction(fail)
        run_on_successful_transaction(lambda: calls.append('run'))
        with caplog.at_level(logging.ERROR):
            session.commit()
        # the commit stands, the other operations still run
        assert calls == ['run']
        assert 'Scheduled operation failed' in caplog.text


class TestCommitOrRollback:
    def test_commit(self, session):
        calls = []
        run_on_successful_transaction(lambda: calls.append('run'))
        with commit_or_rollback(session):
            pass
        assert calls == ['run']

    def test_rollback_on_error(self, session):
        calls = []
        run_on_successful_transaction(lambda: calls.append('run'))
        with pytest.raises(ValueError), commit_or_rollback(session):
            raise ValueError
        assert calls == []
