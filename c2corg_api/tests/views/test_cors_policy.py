import unittest

from c2corg_api.views import (
    DEFAULT_CORS_ORIGINS,
    configure_cors_policy,
    cors_policy,
)


class ConfigureCorsPolicyTest(unittest.TestCase):
    """
    Test `configure_cors_policy`, saving/restoring `cors_policy` state.

    `cors_policy` is a module-level dict shared (by reference) with every
    `@resource`-decorated view, and mutated in place by
    `configure_cors_policy`. Save/restore it around each test so that
    tests don't leak state into each other or into the rest of the suite.
    """

    def setUp(self):
        self._original_origins = cors_policy['origins']

    def tearDown(self):
        cors_policy['origins'] = self._original_origins

    def test_never_configures_a_wildcard(self):
        # No matter the settings, a bare "*" must never come out of this,
        # since the API accepts the Authorization header cross-origin.
        configure_cors_policy({'cors.allowed_origins': '*'})
        self.assertNotIn('*', cors_policy['origins'])

    def test_parses_space_separated_origins(self):
        configure_cors_policy({
            'cors.allowed_origins':
                'https://www.camptocamp.org https://demov6.camptocamp.org'
        })
        self.assertEqual(
            cors_policy['origins'],
            ('https://www.camptocamp.org', 'https://demov6.camptocamp.org'))

    def test_falls_back_to_default_when_setting_missing(self):
        configure_cors_policy({})
        self.assertEqual(cors_policy['origins'], DEFAULT_CORS_ORIGINS)

    def test_falls_back_to_default_when_setting_blank(self):
        configure_cors_policy({'cors.allowed_origins': '   '})
        self.assertEqual(cors_policy['origins'], DEFAULT_CORS_ORIGINS)


if __name__ == '__main__':
    unittest.main()
