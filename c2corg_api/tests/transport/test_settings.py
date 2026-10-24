import os
from unittest import mock

from c2corg_api.transport import dedup, gtfs, linking
from c2corg_api.transport.settings import env_float, env_int

NAME = 'TRANSPORT_TEST_THRESHOLD'


def environ(**values):
    return mock.patch.dict(os.environ, values, clear=False)


class TestEnv:
    def setup_method(self):
        os.environ.pop(NAME, None)

    def test_default_when_not_set(self):
        assert env_int(NAME, 15) == 15
        assert env_float(NAME, 0.9) == 0.9

    def test_value_of_the_environment(self):
        with environ(**{NAME: '30'}):
            assert env_int(NAME, 15) == 30
            assert env_float(NAME, 0.9) == 30.0
        with environ(**{NAME: ' 0.75 '}):
            assert env_float(NAME, 0.9) == 0.75

    def test_default_when_empty(self):
        with environ(**{NAME: ''}):
            assert env_int(NAME, 15) == 15
        with environ(**{NAME: '  '}):
            assert env_float(NAME, 0.9) == 0.9

    def test_default_when_not_a_number(self):
        with environ(**{NAME: 'far'}):
            assert env_int(NAME, 15) == 15
        with environ(**{NAME: '1.5'}):
            # an integer is expected
            assert env_int(NAME, 15) == 15

    def test_default_out_of_the_limits(self):
        with environ(**{NAME: '0'}):
            assert env_int(NAME, 15, minimum=1) == 15
        with environ(**{NAME: '1.5'}):
            assert env_float(NAME, 0.9, minimum=0, maximum=1) == 0.9
        with environ(**{NAME: '1'}):
            assert env_float(NAME, 0.9, minimum=0, maximum=1) == 1.0


class TestDefaults:
    """The thresholds without the environment."""

    def test_thresholds_of_the_modules(self):
        # the tests load the default .env, which has the same values
        assert dedup.SAME_PLACE_DISTANCE == 15
        assert dedup.NEAR_DISTANCE == 50
        assert dedup.LINE_TOLERANCE == 25
        assert dedup.LINE_OVERLAP == 0.9
        assert linking.MAX_DISTANCE == 50
        assert gtfs.SIMPLIFY_TOLERANCE == 5
        assert gtfs.MAX_VARIANTS_PER_DIRECTION == 6
        assert gtfs.SERVICE_DAYS == 365
