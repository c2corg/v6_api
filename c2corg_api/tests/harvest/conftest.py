from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from c2corg_api.harvest import runner


class Clock:
    """The time of the runner, moved by the tests."""

    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock(datetime(2026, 11, 24, 11, tzinfo=UTC))
    monkeypatch.setattr(runner, '_now', clock)
    # no jitter
    monkeypatch.setattr(runner.random, 'random', lambda: 0.0)
    return clock


@pytest.fixture
def harvest_session(db_connection):
    """Return a session to check what the runner wrote, in the test's transaction."""
    # The sessions of the runner then work in savepoints of the test's
    # transaction: the rollback of one (a failed store) does not end it.
    db_connection.begin_nested()
    session = Session(bind=db_connection)
    yield session
    session.close()
