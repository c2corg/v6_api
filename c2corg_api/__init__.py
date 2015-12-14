import logging

from pyramid.config import Configurator
from sqlalchemy import engine_from_config
from pyramid.httpexceptions import HTTPUnauthorized

from c2corg_api.models import (
    DBSession,
    Base,
    )
from c2corg_api.search import configure_es_from_config

from pyramid.security import Allow, Everyone, Authenticated

from c2corg_api.security.roles import is_valid_token, extract_token

from pyramid.settings import asbool

log = logging.getLogger(__name__)


class RootFactory(object):
    __name__ = 'RootFactory'
    __acl__ = [
            (Allow, Everyone, 'public'),
            (Allow, Authenticated, 'authenticated'),
            (Allow, 'group:moderators', 'moderator')
    ]

    def __init__(self, request):
        pass


def jwt_database_validation_tween_factory(handler, registry):
    """ Check validity of the JWT token.
    """

    def tween(request):
        # TODO: first set the cookie in request.authorization if needed

        # Then forward requests without authorization
        if request.authorization is None:
            # Skipping validation if there is no authorization object.
            # This is dangerous since a bad ordering of this tween and the
            # cookie tween would bypass security
            return handler(request)

        # Finally, check database validation
        token = extract_token(request)
        valid = token and is_valid_token(token)

        if valid:
            return handler(request)
        else:
            # TODO: clear cookie? send json?
            return HTTPUnauthorized("Invalid token")

    return tween


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """

    # Configure SQLAlchemy
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    # Configure ElasticSearch
    configure_es_from_config(settings)

    config = Configurator(settings=settings)

    # Add routes not handled by Cornice
    config.add_route('login', '/login')
    config.add_route('logout', '/logout')
    config.add_route('check_token', '/check_token')

    config.include('cornice')

    bypass_auth = False
    if 'noauthorization' in settings:
        bypass_auth = asbool(settings['noauthorization'])

    if not bypass_auth:
        config.include("pyramid_jwtauth")
        # Intercept request handling to validate token against the database
        config.add_tween('c2corg_api.jwt_database_validation_tween_factory')
        # Inject ACLs
        config.set_root_factory(RootFactory)
    else:
        log.warning('Bypassing authorization')

    # Scan MUST be the last call otherwise ACLs will not be set
    # and the permissions would be bypassed
    config.scan(ignore='c2corg_api.tests')
    return config.make_wsgi_app()
