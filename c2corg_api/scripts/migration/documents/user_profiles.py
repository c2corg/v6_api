from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.models.user_profile import UserProfile, ArchiveUserProfile, \
    USERPROFILE_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes
from sqlalchemy.sql.expression import text
import transaction


class MigrateUserProfiles(MigrateDocuments):

    def get_name(self):
        return 'user profiles'

    def get_model_document(self, locales):
        return DocumentLocale if locales else UserProfile

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveUserProfile

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_users_archives ua '
            '  join users u on ua.id = u.id '
            '  join app_users_private_data au on ua.id = au.id '
            'where u.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   ua.id, ua.document_archive_id, ua.is_latest_version, '
            '   ua.is_protected, ua.redirects_to, '
            '   ST_Force2D(ST_SetSRID(ua.geom, 3857)) geom, '
            '   ua.activities, ua.category '
            'from app_users_archives ua '
            '  join users u on ua.id = u.id '
            '  join app_users_private_data au on ua.id = au.id '
            'where u.redirects_to is null '
            'order by ua.id, ua.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_users_i18n_archives ua '
            '  join users u on ua.id = u.id '
            '  join app_users_private_data au on ua.id = au.id '
            'where u.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   ua.id, ua.document_i18n_archive_id, ua.is_latest_version, '
            '   ua.culture, ua.description '
            'from app_users_i18n_archives ua '
            '  join users u on ua.id = u.id '
            '  join app_users_private_data au on ua.id = au.id '
            'where u.redirects_to is null '
            'order by ua.id, ua.culture, ua.document_i18n_archive_id;'
        )

    query_profileless_users = (
        'select pu.id '
        'from app_users_private_data pu left outer join users u '
        '  on pu.id = u.id and u.redirects_to is null '
        'where u.id is null;'
    )

    def migrate(self):
        super(MigrateUserProfiles, self).migrate()

        # some users to do not have a profile, create an empty profile so that
        # the users can be imported.
        with transaction.manager:
            last_locale_id = self.connection_source.execute(
                text('select max(document_i18n_archive_id) '
                     'from app_documents_i18n_archives;')).fetchone()[0]
            last_archive_id = self.connection_source.execute(
                text('select max(document_archive_id) '
                     'from app_documents_archives;')).fetchone()[0]

            profileless_users = self.connection_source.execute(
                text(MigrateUserProfiles.query_profileless_users))
            for row in profileless_users:
                user_id = row[0]
                last_locale_id += 1
                last_archive_id += 1

                locale = DocumentLocale(
                    id=last_locale_id,
                    document_id=user_id,
                    lang='fr', title=''
                )
                profile = UserProfile(
                    document_id=user_id,
                    locales=[locale]
                )
                locale_archive = locale.to_archive()
                locale_archive.id = last_locale_id
                profile_archive = profile.to_archive()
                profile_archive.id = last_archive_id

                self.session_target.add(profile)
                self.session_target.add(locale)
                self.session_target.flush()
                self.session_target.add(locale_archive)
                self.session_target.add(profile_archive)

    def get_document(self, document_in, version):
        categories = [document_in.category] \
            if document_in.category is not None else None
        return dict(
            document_id=document_in.id,
            type=USERPROFILE_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            activities=self.convert_types(
                document_in.activities, MigrateRoutes.activities),
            categories=self.convert_types(
                categories, MigrateUserProfiles.user_categories,
                skip_values=[0, 2, 5]),
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=DOCUMENT_TYPE,
            version=version,
            lang=document_in.culture,
            # do not set the title (in v5 the title of an user profile was the
            # topo-guide username. this name was also stored on the user itself
            # and was copied to the locale when it was changed. to simplify
            # things, the name is now only stored on the user.)
            title='',
            description=description,
            summary=summary
        )

    user_categories = {
        '1': 'amateur',
        '3': 'club',
        '4': 'institution',
    }
