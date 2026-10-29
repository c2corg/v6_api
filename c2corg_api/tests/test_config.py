import os

import pytest

from c2corg_api.config import asbool, get_appsettings, parse_vars

TEST_INI = os.path.join(os.path.dirname(__file__), '../../test.ini')


class TestGetAppsettings:
    def test_settings_of_the_app_section(self):
        settings = get_appsettings(TEST_INI)
        # from test.ini, and from common.ini through `use = config:common.ini`
        assert settings['sqlalchemy.url'].startswith('postgresql+psycopg2://')
        assert 'jwt.private_key' in settings
        assert 'use' not in settings

    def test_options(self):
        settings = get_appsettings(TEST_INI, options={'unused': '1'})
        assert settings == get_appsettings(TEST_INI)


class TestParseVars:
    def test_assignments(self):
        assert parse_vars(['a=b', 'c=d=e']) == {'a': 'b', 'c': 'd=e'}

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_vars(['a'])


class TestAsbool:
    @pytest.mark.parametrize('value', ['true', 'True', ' yes ', 'on', '1', 't', True])
    def test_true(self, value):
        assert asbool(value) is True

    @pytest.mark.parametrize('value', ['false', 'no', '0', '', None, False, 'other'])
    def test_false(self, value):
        assert asbool(value) is False
