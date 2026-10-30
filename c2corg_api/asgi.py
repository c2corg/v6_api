"""The ASGI application of the API, for uvicorn."""
# Served with
#   gunicorn -k uvicorn_worker.UvicornWorker c2corg_api.asgi:app
# The settings and the logging come from the .ini file named by
# C2C_API_CONFIG, production.ini by default, as `--paste production.ini`
# reads them for the WSGI application.

import os

from c2corg_api import create_app
from c2corg_api.config import get_appsettings, setup_logging

CONFIG = os.environ.get('C2C_API_CONFIG', 'production.ini')

setup_logging(CONFIG)
app = create_app(get_appsettings(CONFIG))
