"""The log line of the route duration hook."""

import logging

import pytest

from c2corg_api import _update_route_duration


class _Connection:
    def execute(self, *args):
        pass


@pytest.mark.parametrize(
    'duration, logged',
    [(0.25, '0.25 days'), (None, 'None days')],
)
def test_logs_the_stored_duration(caplog, duration, logged):
    with caplog.at_level(logging.INFO, logger='c2corg_api'):
        _update_route_duration(_Connection(), 1, duration)
    assert (
        f'Route 1: Database updated with calculated_duration = {logged}.'
        in caplog.messages
    )
