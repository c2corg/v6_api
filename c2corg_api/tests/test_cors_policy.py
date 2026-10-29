import json
import subprocess  # nosec B404 (the Python of the tests, a constant script)
import sys

# The allowed CORS origins are a setting, read at start-up into a module
# dict: the check runs in a new process, with an origin that is not the
# default one (the origin of the tests), else a setting that is not applied
# goes unnoticed.
SCRIPT = """
import json
from webtest import TestApp
from c2corg_api import main
from c2corg_api.tests import settings

settings = dict(settings)
settings['cors.allowed_origins'] = 'https://www.example.org'
app = TestApp(main({}, **settings))
print(json.dumps([
    app.get('/health', headers={'Origin': origin}, status='*').headers.get(
        'Access-Control-Allow-Origin'
    )
    for origin in ('https://www.example.org', 'http://localhost:6553')
]))
"""


def test_the_configured_origins_are_allowed():
    result = subprocess.run(  # nosec B603 (sys.executable, a constant script)
        [sys.executable, '-c', SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    allowed = json.loads(result.stdout.strip().splitlines()[-1])
    # the configured origin, and no longer the default one
    assert allowed == ['https://www.example.org', None]
