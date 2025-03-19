import logging

from c2corg_api.caching import configure_caches
from pyramid.config import Configurator
from sqlalchemy import engine_from_config, exc, event
from sqlalchemy.pool import Pool

from c2corg_api.models import DBSession, Base
from c2corg_api.queues.queues_service import get_queue_config
from c2corg_api.search import configure_es_from_config

from pyramid.security import Allow, Everyone, Authenticated

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
    config.include('cornice')
    config.registry.queue_config = get_queue_config(
        settings,
        settings['redis.queue_es_sync']
    )

    # Configure documents views queue
    config.registry.documents_views_queue_config = (
        get_queue_config(
            settings,
            settings['redis.queue_documents_views_sync']
        )
    )

    # FIXME? Make sure this tween is run after the JWT validation
    # Using an explicit ordering in config files might be needed.
    config.add_tween('c2corg_api.tweens.rate_limiting.' +
                     'rate_limiting_tween_factory',
                     under='pyramid_tm.tm_tween_factory')

    bypass_auth = False
    if 'noauthorization' in settings:
        bypass_auth = asbool(settings['noauthorization'])

    if not bypass_auth:
        config.include("pyramid_jwtauth")
        # Intercept request handling to validate token against the database
        config.add_tween('c2corg_api.tweens.jwt_database_validation.' +
                         'jwt_database_validation_tween_factory')
        # Inject ACLs
        config.set_root_factory(RootFactory)
    else:
        log.warning('Bypassing authorization')

    configure_caches(settings)
    configure_feed(settings, config)
    configure_anonymous(settings, config)

    # Scan MUST be the last call otherwise ACLs will not be set
    # and the permissions would be bypassed
    config.scan(ignore='c2corg_api.tests')
    return config.make_wsgi_app()


# validate db connection before using it
@event.listens_for(Pool, 'checkout')
def ping_connection(dbapi_connection, connection_record, connection_proxy):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('SELECT 1')
    except Exception:
        # raise DisconnectionError - pool will try
        # connecting again up to three times before raising.
        raise exc.DisconnectionError()
    cursor.close()


def configure_feed(settings, config):
    account_id = None

    if settings.get('feed.admin_user_account'):
        account_id = int(settings.get('feed.admin_user_account'))
    config.registry.feed_admin_user_account_id = account_id


def configure_anonymous(settings, config):
    account_id = None

    if settings.get('guidebook.anonymous_user_account'):
        account_id = int(settings.get('guidebook.anonymous_user_account'))
    config.registry.anonymous_user_id = account_id
