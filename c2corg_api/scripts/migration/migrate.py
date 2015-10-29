import os
import sys
import logging
from sqlalchemy.orm import sessionmaker
from zope.sqlalchemy import ZopeTransactionExtension
from sqlalchemy import engine_from_config
from pyramid.paster import get_appsettings

from c2corg_api.models import Base
from c2corg_api.scripts.initializedb import setup_db
from c2corg_api.scripts.migration.documents.summit import MigrateSummits
from c2corg_api.scripts.migration.documents.versions import MigrateVersions


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
    MigrateSummits(connection_source, session, batch_size).migrate()
    MigrateVersions(connection_source, session, batch_size).migrate()

if __name__ == "__main__":
    main()
