import transaction
import zope

from sqlalchemy.sql import text

from c2corg_api.scripts.migration.migrate_base import MigrateBase
from c2corg_api.scripts.migration.batch import SimpleBatch

from c2corg_api.models import sympa_schema
from c2corg_api.models.mailinglist import Mailinglist


class MigrateMailinglists(MigrateBase):
    """Initialize the mailing lists table with subscriptions from v5.
    """

    def migrate(self):
        self.start('Mailing lists subscriptions')

        total_count = self.connection_source.execute(
                    text(SQL_ML_QUERY_COUNT)).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text(SQL_ML_QUERY)
        batch = SimpleBatch(
            self.session_target, self.batch_size, Mailinglist)
        with transaction.manager, batch:
            count = 0
            for entity_in in self.connection_source.execute(query):
                count += 1
                batch.add(self.get_subscription(entity_in))
                self.progress(count, total_count)
            zope.sqlalchemy.mark_changed(self.session_target)

        # run analyze on the table (must be outside a transaction)
        engine = self.session_target.bind
        conn = engine.connect()
        old_lvl = conn.connection.isolation_level
        conn.connection.set_isolation_level(0)
        conn.execute('analyze ' + sympa_schema + '.subscriber_table;')
        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()

    def get_subscription(self, row):
        return dict(
            listname=row.list_subscriber,
            email=row.user_subscriber,
            user_id=row.user_id,
            date_subscriber=row.date_subscriber,
            update_subscriber=row.update_subscriber,
            visibility_subscriber=row.visibility_subscriber,
            reception_subscriber=row.reception_subscriber,
            bounce_subscriber=row.bounce_subscriber,
            bounce_score_subscriber=row.bounce_score_subscriber,
            comment_subscriber=row.comment_subscriber,
            subscribed_subscriber=row.subscribed_subscriber,
            included_subscriber=row.included_subscriber,
            include_sources_subscriber=row.include_sources_subscriber
        )


SQL_ML_QUERY_COUNT = """
select count(*) from subscriber_table ml
join app_users_private_data u on ml.user_subscriber = u.email;
"""

SQL_ML_QUERY = """
select list_subscriber, user_subscriber, u.id as user_id,
date_subscriber, update_subscriber, visibility_subscriber,
reception_subscriber, bounce_subscriber, bounce_score_subscriber,
comment_subscriber, subscribed_subscriber, included_subscriber,
include_sources_subscriber
from subscriber_table ml join app_users_private_data u
on ml.user_subscriber = u.email;
"""
