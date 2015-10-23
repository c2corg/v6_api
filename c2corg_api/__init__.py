from pyramid.config import Configurator
from sqlalchemy import engine_from_config

from c2corg_api.models import (
    DBSession,
    Base,
    )
from c2corg_api.views import cors_policy


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine
    config = Configurator(settings=settings)

    origins = settings['cors.origins']
    cors_policy['origins'] = origins.split(',')

    config.include('cornice')
    config.scan(ignore='c2corg_api.tests')

    return config.make_wsgi_app()
