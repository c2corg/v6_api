from c2corg_api.models.area import Area
from c2corg_api.models.feed import FilterArea
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes
from sqlalchemy.sql import text
import transaction
import zope
from urllib import parse

from c2corg_api.models.user import User
from c2corg_api.scripts.migration.migrate_base import MigrateBase, \
    parse_php_object
from c2corg_api.scripts.migration.batch import SimpleBatch


class MigrateUsers(MigrateBase):
    """Migrate user data.
    Roles are stored directly as boolean columns.
    Super admins and plain admins are merged together.
    """

    def __init__(self, connection_source, session_target, batch_size):
        super(MigrateUsers, self).__init__(
            connection_source, session_target, batch_size)

    def migrate(self):
        self.start('users')

        query_count = text('select count(*) from app_users_private_data')
        total_count = self.connection_source.execute(query_count).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text('select id, login_name, topo_name, email, '
                     'password, username as forum_username, pref_cookies '
                     'from app_users_private_data order by id')

        def get_group_by_id(gid):
            results = self.connection_source.execute(text(
                'select user_id from app_users_groups where '
                'group_id = ' + str(gid))).fetchall()
            return [r[0] for r in results]

        filter_areas_for_users = []
        batch = SimpleBatch(self.session_target, self.batch_size, User)
        with transaction.manager, batch:
            count = 0
            super_admins = get_group_by_id(1)
            admins = get_group_by_id(2)
            pending = get_group_by_id(4)
            # skipping useless logged/3 (everyone)
            # TODO: inactive = group_query_builder(5)

            for user_in in self.connection_source.execute(query):
                count += 1
                id = user_in.id

                preferences = self.parse_preferences(user_in.pref_cookies, id)
                filter_areas = self.get_areas(
                    preferences.get('filtered_places'))
                filter_areas_for_users.extend(
                    [(id, area_id) for area_id in filter_areas])
                filter_activities = self.get_activities(
                    preferences.get('filtered_activities'))

                batch.add(dict(
                    id=user_in.id,
                    username=user_in.login_name,
                    name=user_in.topo_name,
                    forum_username=user_in.forum_username,
                    email=user_in.email,
                    _password=user_in.password,
                    moderator=id in super_admins or id in admins,
                    email_validated=id not in pending,
                    feed_filter_activities=filter_activities
                    ))
                self.progress(count, total_count)

            # the transaction will not be commited automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)

        # add the area filter rows after all users have been created
        all_area_ids = set(
            area_id for area_id, in
            self.session_target.query(Area.document_id).all()
        )

        batch_filter_area = SimpleBatch(
            self.session_target, self.batch_size, FilterArea)
        with transaction.manager, batch_filter_area:
            for user_id, area_id in filter_areas_for_users:
                # some areas used in the preferences do no longer exist,
                # ignore them
                if area_id in all_area_ids:
                    batch_filter_area.add(dict(
                        user_id=user_id,
                        area_id=area_id))
            zope.sqlalchemy.mark_changed(self.session_target)

        self.stop()

    def parse_preferences(self, pref_cookies_serialized, id):
        """Convert `pref_cookies` which were stored as serialized PHP
        objects to a dict.
        """
        if not pref_cookies_serialized:
            return {}

        try:
            return parse_php_object(pref_cookies_serialized)
        except Exception as e:
            print(pref_cookies_serialized)
            print(id)
            raise e

    def get_areas(self, places_raw):
        """Convert the places string of the preferences cookie into a list of
        area ids:
        '14410%2C14427%2C14417' -> [14410, 14427, 14417]
        """
        if not places_raw:
            return []

        area_ids_raw = parse.unquote(places_raw).split(',')
        return [
            int(id_raw) for id_raw in area_ids_raw
        ]

    def get_activities(self, activities_raw):
        """Convert the activities string of the preferences cookie into a list
        of activity enum values.
        """
        if not activities_raw:
            return []

        activities_raw = parse.unquote(activities_raw).split(',')
        return self.convert_types(activities_raw, MigrateRoutes.activities)
