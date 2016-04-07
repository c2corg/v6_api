from sqlalchemy.sql import text
import transaction
import zope

from c2corg_api.models.user import User
from c2corg_api.scripts.migration.migrate_base import MigrateBase
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
                     'password, username as forum_username '
                     'from app_users_private_data order by id')

        def get_group_by_id(gid):
            return self.connection_source.execute(text(
                'select user_id from app_users_groups where '
                'group_id = ' + str(gid)))

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
                batch.add(dict(
                    id=user_in.id,
                    username=user_in.login_name,
                    name=user_in.topo_name,
                    forum_username=user_in.forum_username,
                    email=user_in.email,
                    _password=user_in.password,
                    moderator=id in super_admins or id in admins,
                    email_validated=id not in pending
                    ))
                self.progress(count, total_count)

            # the transaction will not be commited automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)
        self.stop()
