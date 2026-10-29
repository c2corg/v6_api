"""Read the settings and the logging configuration of the `.ini` files."""
# As pyramid.paster did for the scripts: the settings are those of the
# [app:main] section (with `use = config:common.ini`), read by PasteDeploy,
# which also loads the application for gunicorn (`--paste`).

import logging
import logging.config
import os
from configparser import ConfigParser

from paste.deploy import appconfig

TRUTHY = frozenset({'t', 'true', 'y', 'yes', 'on', '1'})


def _defaults(path, options=None):
    """Return the variables an `.ini` file can use (%(here)s...)."""
    return {
        '__file__': path,
        'here': os.path.dirname(path),
        **(options or {}),
    }


def get_appsettings(config_uri, options=None):
    """Return the settings of the application of an `.ini` file."""
    path = os.path.abspath(config_uri)
    conf = appconfig(
        f'config:{path}', name='main', global_conf=_defaults(path, options)
    )
    return dict(conf.local_conf)


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
