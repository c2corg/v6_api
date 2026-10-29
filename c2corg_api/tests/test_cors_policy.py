import json
import subprocess
import sys

# Cornice copies the allowed CORS origins when a @resource is created, that
# is when its view module is imported: once per process. The check runs in a
# new process, with an origin that is not the default one, else a view module
# imported before configure_cors_policy keeps the default origin unnoticed.
SCRIPT = """
import json
from cornice.service import get_services
from c2corg_api import main
from c2corg_api.tests import settings

settings = dict(settings)
settings['cors.allowed_origins'] = 'https://www.example.org'
main({}, **settings)
print(json.dumps(sorted(
    service.name
    for service in get_services()
    if 'https://www.example.org' not in (service.cors_origins or ())
)))
"""


def test_every_view_allows_the_configured_origins():
    result = subprocess.run(
        [sys.executable, '-c', SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    without_origin = json.loads(result.stdout.strip().splitlines()[-1])
    assert without_origin == []
