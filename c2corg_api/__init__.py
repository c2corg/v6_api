from pyramid.config import Configurator
from sqlalchemy import engine_from_config

from c2corg_api.models import (
    DBSession,
    Base,
    )


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine
    config = Configurator(settings=settings)
    config.include('cornice')
    config.scan(ignore='c2corg_api.tests')
    return config.make_wsgi_app()
