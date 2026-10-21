import os
import unittest
from unittest import mock

from c2corg_api.transport import dedup, gtfs, linking
from c2corg_api.transport.settings import env_float, env_int

NAME = 'TRANSPORT_TEST_THRESHOLD'


def environ(**values):
    return mock.patch.dict(os.environ, values, clear=False)


class TestEnv(unittest.TestCase):

    def setUp(self):  # noqa
        os.environ.pop(NAME, None)

    def test_default_when_not_set(self):
        self.assertEqual(env_int(NAME, 15), 15)
        self.assertEqual(env_float(NAME, 0.9), 0.9)

    def test_value_of_the_environment(self):
        with environ(**{NAME: '30'}):
            self.assertEqual(env_int(NAME, 15), 30)
            self.assertEqual(env_float(NAME, 0.9), 30.0)
        with environ(**{NAME: ' 0.75 '}):
            self.assertEqual(env_float(NAME, 0.9), 0.75)

    def test_default_when_empty(self):
        with environ(**{NAME: ''}):
            self.assertEqual(env_int(NAME, 15), 15)
        with environ(**{NAME: '  '}):
            self.assertEqual(env_float(NAME, 0.9), 0.9)

    def test_default_when_not_a_number(self):
        with environ(**{NAME: 'far'}):
            self.assertEqual(env_int(NAME, 15), 15)
        with environ(**{NAME: '1.5'}):
            # an integer is expected
            self.assertEqual(env_int(NAME, 15), 15)

    def test_default_out_of_the_limits(self):
        with environ(**{NAME: '0'}):
            self.assertEqual(env_int(NAME, 15, minimum=1), 15)
        with environ(**{NAME: '1.5'}):
            self.assertEqual(env_float(NAME, 0.9, minimum=0, maximum=1), 0.9)
        with environ(**{NAME: '1'}):
            self.assertEqual(env_float(NAME, 0.9, minimum=0, maximum=1), 1.0)


class TestDefaults(unittest.TestCase):
    """The thresholds without the environment."""

    def test_thresholds_of_the_modules(self):
        # the tests load the default .env, which has the same values
        self.assertEqual(dedup.SAME_PLACE_DISTANCE, 15)
        self.assertEqual(dedup.NEAR_DISTANCE, 50)
        self.assertEqual(dedup.LINE_TOLERANCE, 25)
        self.assertEqual(dedup.LINE_OVERLAP, 0.9)
        self.assertEqual(linking.MAX_DISTANCE, 50)
        self.assertEqual(gtfs.SIMPLIFY_TOLERANCE, 5)
        self.assertEqual(gtfs.MAX_VARIANTS_PER_DIRECTION, 6)
        self.assertEqual(gtfs.SERVICE_DAYS, 365)
