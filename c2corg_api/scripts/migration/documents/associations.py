from sqlalchemy.sql import text
import transaction
import zope

from c2corg_api.scripts.migration.documents.versions import tables_union
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.scripts.migration.batch import SimpleBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase

# TODO currently only importing associations for waypoints and routes
associations_query_count =\
    'select count(*) from (' \
    '  select a.main_id, a.linked_id from app_documents_associations a ' \
    '  inner join (' + tables_union + \
    '  ) u on u.id = a.main_id ' \
    '  inner join (' + tables_union + \
    '  ) v on v.id = a.linked_id ' \
    '  group by a.main_id, a.linked_id) t;'

associations_query = \
    'select main_id, linked_id from app_documents_associations a ' \
    'inner join (' + tables_union + \
    ') u on u.id = a.main_id ' \
    'inner join (' + tables_union + \
    ') v on v.id = a.linked_id ' \
    'group by a.main_id, a.linked_id;'

association_log_query_count =\
    'select count(*) from (' \
    '  select associations_log_id from app_associations_log a ' \
    '  inner join (' + tables_union + \
    '  ) u on u.id = a.main_id ' \
    '  inner join (' + tables_union + \
    '  ) v on v.id = a.linked_id ' \
    '  group by associations_log_id) t;'

association_log_query = \
    'select ' \
    '  associations_log_id, main_id, linked_id, user_id, is_creation, ' \
    '  written_at from app_associations_log a ' \
    'inner join (' + tables_union + \
    ') u on u.id = a.main_id ' \
    'inner join (' + tables_union + \
    ') v on v.id = a.linked_id ' \
    'group by associations_log_id;'


class MigrateAssociations(MigrateBase):
    """Migrate associations and association log. And also set the main waypoint
    and `title_prefix` for routes.
    """

    def migrate(self):
        self._migrate(
            'associations',
            associations_query_count, associations_query, Association,
            self.get_association)
        self._migrate(
            'associations_log',
            association_log_query_count, association_log_query, AssociationLog,
            self.get_log)
        self._set_route_main_waypoint()
        self._set_route_locale_title_prefix()

    def get_association(self, row):
        return dict(
            parent_document_id=row.main_id,
            child_document_id=row.linked_id
        )

    def get_log(self, row):
        return dict(
            parent_document_id=row.main_id,
            child_document_id=row.linked_id,
            user_id=row.user_id,
            is_creation=row.is_creation,
            written_at=row.written_at
        )

    def _migrate(self, label, query_count, query, model, get_entity):
        self.start(label)

        total_count = self.connection_source.execute(
            text(query_count)).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text(query)
        batch = SimpleBatch(
            self.session_target, self.batch_size, model)
        with transaction.manager, batch:
            count = 0
            for entity_in in self.connection_source.execute(query):
                count += 1
                batch.add(get_entity(entity_in))
                self.progress(count, total_count)

            # the transaction will not be committed automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)
        self.stop()

    def _set_route_main_waypoint(self):
        """Set the field `main_waypoint_id` to the highest associated waypoint.
        """
        print('Set main waypoint for routes')
        with transaction.manager:
            self.session_target.execute(SQL_SET_MAIN_WAYPOINT_ID)
            zope.sqlalchemy.mark_changed(self.session_target)
        print('Done')

    def _set_route_locale_title_prefix(self):
        """Set the `title_prefix` field for all route locales that have a
        main waypoint. First set the field for route locales, where there is
        a locale of the main waypoint in the same culture. Then with a 2nd
        query set the remaining rows by selecting the "best" locale of the main
        waypoint.
        """
        with transaction.manager:
            print('Set title prefix for route locales (same culture)')
            self.session_target.execute(SQL_SET_TITLE_PREFIX_SAME_CULTURE)
            print('Set title prefix for route locales (other culture)')
            self.session_target.execute(SQL_SET_TITLE_PREFIX_OTHER_CULTURE)
            zope.sqlalchemy.mark_changed(self.session_target)
        print('Done')


SQL_SET_MAIN_WAYPOINT_ID = """
with v as (select t.r_id, t.w_id
  from (select
    u.r_id, u.w_id, dense_rank() over(
      partition by u.r_id order by u.elevation desc) as rank
    from ((select r.document_id as r_id, wp.document_id as w_id, wp.elevation
      from guidebook.documents r
        join guidebook.associations a on r.document_id = a.parent_document_id
        join guidebook.documents d on a.child_document_id = d.document_id and
          d.type = 'w'
        join guidebook.waypoints wp on d.document_id = wp.document_id
      where r.type = 'r')
    union (select r.document_id as r_id, wp.document_id as w_id, wp.elevation
      from guidebook.documents r
        join guidebook.associations a on r.document_id = a.child_document_id
        join guidebook.documents d on a.parent_document_id = d.document_id and
          d.type = 'w'
        join guidebook.waypoints wp on d.document_id = wp.document_id
      where r.type = 'r')) u
  ) t where t.rank = 1)
update guidebook.routes r
  set main_waypoint_id = v.w_id
from v
where v.r_id = r.document_id;"""

SQL_SET_TITLE_PREFIX_SAME_CULTURE = """
with v as (select rl.id, l2.title
  from guidebook.routes_locales rl join guidebook.documents_locales l1
    on rl.id = l1.id
  join guidebook.routes r on l1.document_id = r.document_id
  join guidebook.documents_locales l2
    on r.main_waypoint_id = l2.document_id and l2.culture = l1.culture)
update guidebook.routes_locales l
  set title_prefix = v.title
from v
where v.id = l.id;
"""

SQL_SET_TITLE_PREFIX_OTHER_CULTURE = """
with v as (select t.id, t.title
  from (select rl.id, l2.title, dense_rank() over(
    partition by rl.id
    order by
      l2.culture != 'fr',
      l2.culture != 'en',
      l2.culture != 'it',
      l2.culture != 'de',
      l2.culture != 'es',
      l2.culture != 'ca'
    ) as rank
    from guidebook.routes_locales rl join guidebook.documents_locales l1
      on rl.id = l1.id and rl.title_prefix is null
    join guidebook.routes r on l1.document_id = r.document_id
    join guidebook.documents_locales l2
      on r.main_waypoint_id = l2.document_id) t
  where t.rank = 1)
update guidebook.routes_locales l
  set title_prefix = v.title
from v
where v.id = l.id;
"""
