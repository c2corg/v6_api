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

    def test_use_config(self, tmp_path):
        # the settings of the file a `use = config:` names, the file's own win
        (tmp_path / 'common.ini').write_text(
            '[app:main]\na = common\nb = common\n[other]\nc = other\n'
        )
        (tmp_path / 'app.ini').write_text(
            '[app:main]\nuse = config:common.ini\nb = app\nd = %(here)s/x\n'
        )
        assert get_appsettings(str(tmp_path / 'app.ini')) == {
            'a': 'common',
            'b': 'app',
            'd': f'{tmp_path}/x',
        }

    def test_options_as_variables(self, tmp_path):
        (tmp_path / 'app.ini').write_text('[app:main]\na = %(name)s\n')
        settings = get_appsettings(str(tmp_path / 'app.ini'), options={'name': 'x'})
        assert settings == {'a': 'x'}

    def test_without_app_section(self, tmp_path):
        (tmp_path / 'app.ini').write_text('[other]\na = 1\n')
        with pytest.raises(ValueError, match='no \\[app:main\\] section'):
            get_appsettings(str(tmp_path / 'app.ini'))

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            get_appsettings(str(tmp_path / 'missing.ini'))

    def test_loop(self, tmp_path):
        (tmp_path / 'app.ini').write_text('[app:main]\nuse = config:app.ini\n')
        with pytest.raises(ValueError, match='loops back'):
            get_appsettings(str(tmp_path / 'app.ini'))


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
