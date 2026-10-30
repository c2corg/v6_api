import json
import os
import subprocess  # nosec B404 (the Python of the tests, a constant script)
import sys

from c2corg_api.tests import configfile

# c2corg_api.asgi reads its .ini file when it is imported: the check runs in
# a new process, which imports it with the settings of the tests.
SCRIPT = """
import json
from a2wsgi import ASGIMiddleware
from webtest import TestApp
from c2corg_api.asgi import app

client = TestApp(ASGIMiddleware(app))
print(json.dumps({
    'type': type(app).__name__,
    'db': app.state.registry.settings['sqlalchemy.url'],
    'unknown': client.get('/nothing/here', status='*').status_int,
    'origin': client.get(
        '/health', headers={'Origin': 'http://localhost:6553'}, status='*'
    ).headers.get('Access-Control-Allow-Origin'),
}))
"""


def _run(env):
    result = subprocess.run(  # nosec B603 (sys.executable, a constant script)
        [sys.executable, '-c', SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
        env={**os.environ, **env},
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_app_of_the_configured_ini_file():
    from c2corg_api.tests import settings

    result = _run({'C2C_API_CONFIG': configfile})
    assert result == {
        'type': 'FastAPI',
        'db': settings['sqlalchemy.url'],
        'unknown': 404,
        'origin': 'http://localhost:6553',
    }
