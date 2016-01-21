import sys
import logging

from c2corg_api.scripts.migration.area_associations import \
    MigrateAreaAssociations
from c2corg_api.scripts.migration.documents.area import MigrateAreas
from c2corg_api.scripts.migration.documents.associations import \
    MigrateAssociations
from c2corg_api.scripts.migration.documents.maps import MigrateMaps
from sqlalchemy import engine_from_config

import os
from sqlalchemy.orm import sessionmaker

from pyramid.paster import get_appsettings

from zope.sqlalchemy import ZopeTransactionExtension
from c2corg_api.models import Base
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


# no-op function referenced from `migration.ini` (required for
# `get_appsettings` to work)
def no_op(global_config, **settings): pass


def main(argv=sys.argv):
    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'migration.ini')
    settings = get_appsettings(settings_file)

    engine_target = engine_from_config(settings, 'sqlalchemy_target.')
    engine_source = engine_from_config(settings, 'sqlalchemy_source.')

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    # create a fresh schema on the target database
    Session = sessionmaker(extension=ZopeTransactionExtension())  # noqa
    session = Session(bind=engine_target)
    Base.metadata.drop_all(engine_target, checkfirst=True)
    setup_db(engine_target, session)

    connection_source = engine_source.connect()

    batch_size = 1000
    MigrateUsers(connection_source, session, batch_size).migrate()
    MigrateSummits(connection_source, session, batch_size).migrate()
    MigrateParkings(connection_source, session, batch_size).migrate()
    MigrateSites(connection_source, session, batch_size).migrate()
    MigrateProducts(connection_source, session, batch_size).migrate()
    MigrateHuts(connection_source, session, batch_size).migrate()
    MigrateRoutes(connection_source, session, batch_size).migrate()
    MigrateMaps(connection_source, session, batch_size).migrate()
    MigrateAreas(connection_source, session, batch_size).migrate()
    MigrateVersions(connection_source, session, batch_size).migrate()
    MigrateAssociations(connection_source, session, batch_size).migrate()
    MigrateAreaAssociations(connection_source, session, batch_size).migrate()
    UpdateSequences(connection_source, session, batch_size).migrate()

if __name__ == "__main__":
    main()
