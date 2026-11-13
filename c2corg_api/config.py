"""Read the settings and the logging configuration of the `.ini` files."""
# The settings are those of the [app:main] section, as PasteDeploy read them:
# `use = config:<file>` takes the [app:main] section of another file first
# (common.ini), the values of the file itself win; `%(here)s` and
# `%(__file__)s` are the directory and the path of the file.

import logging
import logging.config
import os
from configparser import BasicInterpolation, ConfigParser

TRUTHY = frozenset({'t', 'true', 'y', 'yes', 'on', '1'})


def _defaults(path, options=None):
    """Return the variables an `.ini` file can use (%(here)s...)."""
    return {
        '__file__': path,
        'here': os.path.dirname(path),
        **(options or {}),
    }


APP_SECTION = 'app:main'


def get_appsettings(config_uri, options=None):
    """Return the settings of the application of an `.ini` file."""
    # the options (`a=b` on the command line of the scripts) are variables
    # the file can use, not settings
    return _app_settings(os.path.abspath(config_uri), options, ())


def _app_settings(path, options, seen):
    if path in seen:
        raise ValueError(f'{path}: `use = config:` loops back to this file')
    defaults = _defaults(path, options)
    parser = ConfigParser(defaults=defaults, interpolation=BasicInterpolation())
    if not parser.read(path):
        raise FileNotFoundError(path)
    if not parser.has_section(APP_SECTION):
        raise ValueError(f'{path}: no [{APP_SECTION}] section')
    section = parser[APP_SECTION]
    settings = {}
    use = section.get('use', '')
    if use.startswith('config:'):
        base = os.path.join(os.path.dirname(path), use.removeprefix('config:'))
        settings.update(_app_settings(base, options, (*seen, path)))
    for name in parser.options(APP_SECTION):
        if name != 'use' and name not in defaults:
            settings[name] = section[name]
    return settings


def setup_logging(config_uri):
    """Configure the logging as the [loggers] sections of an `.ini` file say."""
    path = os.path.abspath(config_uri)
    parser = ConfigParser()
    parser.read(path)
    if parser.has_section('loggers'):
        logging.config.fileConfig(path, _defaults(path), disable_existing_loggers=False)
    else:
        logging.basicConfig()


def parse_vars(args):
    """Turn ['a=b', 'c=d'] (arguments of a script) into {'a': 'b', 'c': 'd'}."""
    result = {}
    for arg in args:
        if '=' not in arg:
            raise ValueError(f'Variable assignment {arg!r} invalid (no "=")')
        name, value = arg.split('=', 1)
        result[name] = value
    return result


def asbool(value):
    """Return a setting as a boolean: 'true', 'yes', 'on', '1'... are True."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUTHY
