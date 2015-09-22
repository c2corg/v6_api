from pyramid.config import Configurator
from sqlalchemy import engine_from_config

from .models import (
    DBSession,
    Base,
    )

from .ext import caching


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine
    config = Configurator(settings=settings)
    config.include('cornice')

    # dogpile.cache configuration
    # TODO: get config from settings
    # caching.init_region(settings["cache"])
    caching.init_region({'backend': 'dogpile.cache.memory'})
    caching.invalidate_region()

    config.scan(ignore='app_api.tests')
    return config.make_wsgi_app()
