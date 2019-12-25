import sys
import logging

from c2corg_api.scripts.migration.analyze_all_tables import AnalyzeAllTables
from c2corg_api.scripts.migration.area_associations import \
    MigrateAreaAssociations
from c2corg_api.scripts.migration.climbing_site_routes import \
    CreateClimbingSiteRoutes
from c2corg_api.scripts.migration.documents.xreports import MigrateXreports
from c2corg_api.scripts.migration.documents.area import MigrateAreas
from c2corg_api.scripts.migration.documents.associations import \
    MigrateAssociations
from c2corg_api.scripts.migration.documents.maps import MigrateMaps
from c2corg_api.scripts.migration.documents.route_title_prefix import \
    SetRouteTitlePrefix
from c2corg_api.scripts.migration.documents.user_profiles import \
    MigrateUserProfiles
from c2corg_api.scripts.migration.documents.outings import MigrateOutings
from c2corg_api.scripts.migration.documents.images import MigrateImages
from c2corg_api.scripts.migration.documents.articles import MigrateArticles
from c2corg_api.scripts.migration.documents.books import MigrateBooks
from c2corg_api.scripts.migration.map_associations import \
    MigrateMapAssociations
from c2corg_api.scripts.migration.set_default_geometries import \
    SetDefaultGeometries
from sqlalchemy import engine_from_config

import os
from sqlalchemy.orm import sessionmaker

from pyramid.paster import get_appsettings

from zope.sqlalchemy import ZopeTransactionExtension
from c2corg_api.scripts.initializedb import setup_db
from c2corg_api.scripts.migration.users import MigrateUsers
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes
from c2corg_api.scripts.migration.documents.versions import MigrateVersions
from c2corg_api.scripts.migration.documents.waypoints.huts import MigrateHuts
from c2corg_api.scripts.migration.documents.waypoints.parking import \
    MigrateParkings
from c2corg_api.scripts.migration.documents.waypoints.products import \
    MigrateProducts
from c2corg_api.scripts.migration.documents.waypoints.sites import MigrateSites
from c2corg_api.scripts.migration.documents.waypoints.summit import \
    MigrateSummits
from c2corg_api.scripts.migration.sequences import UpdateSequences
from c2corg_api.scripts.migration.init_feed import InitFeed
from c2corg_api.scripts.migration.mailinglists import MigrateMailinglists
from alembic.config import Config


# flake8: noqa

# no-op function referenced from `migration.ini` (required for
# `get_appsettings` to work)
def no_op(global_config, **settings): pass


def main(argv=sys.argv):
    alembic_configfile = os.path.realpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../../../alembic.ini'))
    alembic_config = Config(alembic_configfile)

    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'migration.ini')
    settings = get_appsettings(settings_file)

    engine_target = engine_from_config(settings, 'sqlalchemy_target.')
    engine_source = engine_from_config(settings, 'sqlalchemy_source.')

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    Session = sessionmaker(extension=ZopeTransactionExtension())  # noqa
    session = Session(bind=engine_target)

    # set up the target database
    setup_db(alembic_config, session)

    connection_source = engine_source.connect()

    batch_size = 1000
    MigrateAreas(connection_source, session, batch_size).migrate()
    MigrateUserProfiles(connection_source, session, batch_size).migrate()
    MigrateUsers(connection_source, session, batch_size).migrate()
    MigrateSummits(connection_source, session, batch_size).migrate()
    MigrateParkings(connection_source, session, batch_size).migrate()
    MigrateSites(connection_source, session, batch_size).migrate()
    MigrateProducts(connection_source, session, batch_size).migrate()
    MigrateHuts(connection_source, session, batch_size).migrate()
    MigrateRoutes(connection_source, session, batch_size).migrate()
    MigrateMaps(connection_source, session, batch_size).migrate()
    MigrateOutings(connection_source, session, batch_size).migrate()
    MigrateImages(connection_source, session, batch_size).migrate()
    MigrateXreports(connection_source, session, batch_size).migrate()
    MigrateArticles(connection_source, session, batch_size).migrate()
    MigrateBooks(connection_source, session, batch_size).migrate()
    MigrateVersions(connection_source, session, batch_size).migrate()
    MigrateAssociations(connection_source, session, batch_size).migrate()
    CreateClimbingSiteRoutes(connection_source, session, batch_size).migrate()
    SetRouteTitlePrefix(connection_source, session, batch_size).migrate()
    SetDefaultGeometries(connection_source, session, batch_size).migrate()
    MigrateAreaAssociations(connection_source, session, batch_size).migrate()
    MigrateMapAssociations(connection_source, session, batch_size).migrate()
    MigrateMailinglists(connection_source, session, batch_size).migrate()
    UpdateSequences(connection_source, session, batch_size).migrate()
    InitFeed(connection_source, session, batch_size).migrate()
    AnalyzeAllTables(connection_source, session, batch_size).migrate()

if __name__ == "__main__":
    main()
