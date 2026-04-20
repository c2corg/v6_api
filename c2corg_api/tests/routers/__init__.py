"""
Shared test helpers for FastAPI router tests.
"""

import os

from fastapi import FastAPI


def get_real_app() -> FastAPI:
    """Build the **real** FastAPI application via ``create_app()``.

    ``C2CORG_INI`` is pointed at the test configuration so that
    the database, ElasticSearch, etc. use the test fixtures that
    ``setup_package()`` already prepared.

    The app is cached after the first call so that expensive
    startup work (Pyramid init, DB engine, etc.) is done only
    once per test run.

    ``skip_pyramid=True`` avoids calling ``main()`` a second time
    (``BaseTestCase.setUpClass`` already initialised the Pyramid app
    and bound ``DBSession``).  Re-entering ``main()`` would call
    ``DBSession.configure(bind=engine)`` on an already-active scoped
    session and emit an ``SAWarning``.

    We pass the engine that ``setup_package()`` already bound to
    ``DBSession`` so that ``create_app()`` does not create a
    duplicate engine.
    """
    if get_real_app._app is None:
        os.environ.setdefault(
            'C2CORG_INI',
            os.path.join(os.path.dirname(__file__), '..', '..', '..', 'test.ini'),
        )
        from c2corg_api.models import DBSession

        engine = DBSession.bind

        from c2corg_api.app import create_app

        get_real_app._app = create_app(engine=engine, skip_pyramid=True)
    return get_real_app._app


get_real_app._app = None
