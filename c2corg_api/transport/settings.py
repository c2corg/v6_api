"""Read the thresholds of the public transport from the environment.

The thresholds of the public transport are read from the environment
(see `.env`): they can be changed without changing the code. A variable that
is not set, empty, not a number or out of its limits is ignored, and the
default is used.
"""

import logging
import os

log = logging.getLogger(__name__)


def _get(name, default, cast, minimum, maximum):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        number = cast(value.strip())
    except ValueError:
        log.warning('%s=%r is not a number, using %s', name, value, default)
        return default
    if (minimum is not None and number < minimum) or (
        maximum is not None and number > maximum
    ):
        log.warning(
            '%s=%r is out of its limits (%s to %s), using %s',
            name,
            value,
            minimum,
            maximum,
            default,
        )
        return default
    return number


def env_int(name, default, minimum=None, maximum=None):
    return _get(name, default, int, minimum, maximum)


def env_float(name, default, minimum=None, maximum=None):
    return _get(name, default, float, minimum, maximum)
