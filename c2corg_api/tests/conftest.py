"""
Pytest conftest for c2corg_api tests.

Mocks external HTTP calls to the Navitia API so that tests never depend on
real network access or valid SSL certificates.  All other HTTP requests are
left untouched.
"""
from unittest.mock import patch, MagicMock

import pytest
import requests as _real_requests

NAVITIA_HOST = "api.navitia.io"


def _selective_get(url, *args, **kwargs):
    """Intercept requests.get: return a fake empty response for Navitia
    URLs and fall through to the real implementation for everything else."""
    if NAVITIA_HOST in str(url):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        return mock_resp
    return _real_requests.get(url, *args, **kwargs)


@pytest.fixture(autouse=True)
def mock_navitia_requests():
    """Automatically mock ``requests.get`` calls targeting the Navitia API
    (``api.navitia.io``) so that the ``process_new_waypoint`` SQLAlchemy
    event listener never hits the real endpoint.  Non-Navitia requests are
    forwarded to the real ``requests.get``."""
    with patch("c2corg_api.requests.get", side_effect=_selective_get):
        yield
