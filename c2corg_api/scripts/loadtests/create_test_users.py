import sys
import logging
import transaction

from sqlalchemy import engine_from_config

import os
from sqlalchemy.orm import sessionmaker

from pyramid.paster import get_appsettings

from zope.sqlalchemy import register

from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile


NB_USERS_TO_CREATE = 1000
BASE_USERNAME = 'testuserc2c'


# no-op function referenced from `loadtests.ini` (required for
# `get_appsettings` to work)
def no_op(global_config, **settings): pass


def main(argv=sys.argv):
    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'loadtests.ini')
    settings = get_appsettings(settings_file)

    engine = engine_from_config(settings, 'sqlalchemy.')

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    Session = sessionmaker()  # noqa
    register(Session)
    session = Session(bind=engine)

    with transaction.manager:
        for i in range(1, NB_USERS_TO_CREATE + 1):
            username = BASE_USERNAME + str(i)
            password = username
            email = username + '@foo.bar'
            lang = 'fr'

            profile = UserProfile(
                categories=['amateur'],
                geometry=DocumentGeometry(
                    version=1, geom=None, geom_detail=None),
                locales=[DocumentLocale(lang=lang, title='')]
            )
            user = User(
                username=username,
                forum_username=username,
                name=username,
                email=email,
                lang=lang,
                password=password,
                profile=profile
            )
            # make sure user account is directly validated
            user.clear_validation_nonce()
            user.email_validated = True

            session.add(user)
            session.flush()

            # also create a version for the profile
            # code from DocumentRest.create_new_version
            archive = user.profile.to_archive()
            archive_locales = user.profile.get_archive_locales()
            archive_geometry = user.profile.get_archive_geometry()
            meta_data = HistoryMetaData(comment='creation', user_id=user.id)
            versions = []
            for locale in archive_locales:
                version = DocumentVersion(
                    document_id=user.profile.document_id,
                    lang=locale.lang,
                    document_archive=archive,
                    document_locales_archive=locale,
                    document_geometry_archive=archive_geometry,
                    history_metadata=meta_data
                )
                versions.append(version)
            session.add(archive)
            session.add_all(archive_locales)
            session.add(meta_data)
            session.add_all(versions)
            session.flush()

    print('Created %d users with base username `%s`' % (
        NB_USERS_TO_CREATE, BASE_USERNAME))


if __name__ == "__main__":
    main()
