import transaction
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class SetRouteTitlePrefix(MigrateBase):
    """Set the `title_prefix` field for all route locales that have a
    main waypoint. First set the field for route locales, where there is
    a locale of the main waypoint in the same lang. Then with a 2nd
    query set the remaining rows by selecting the "best" locale of the main
    waypoint.
    """

    def migrate(self):
        self.start('title prefix')

        with transaction.manager:
            print('Set title prefix for route locales (same lang)')
            self.session_target.execute(SQL_SET_TITLE_PREFIX_SAME_CULTURE)
            print('Set title prefix for route locales (other lang)')
            self.session_target.execute(SQL_SET_TITLE_PREFIX_OTHER_CULTURE)
            zope.sqlalchemy.mark_changed(self.session_target)

        self.stop()


SQL_SET_TITLE_PREFIX_SAME_CULTURE = """
with v as (select rl.id, l2.title
  from guidebook.routes_locales rl join guidebook.documents_locales l1
    on rl.id = l1.id
  join guidebook.routes r on l1.document_id = r.document_id
  join guidebook.documents_locales l2
    on r.main_waypoint_id = l2.document_id and l2.lang = l1.lang)
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
      l2.lang != 'fr',
      l2.lang != 'en',
      l2.lang != 'it',
      l2.lang != 'de',
      l2.lang != 'es',
      l2.lang != 'ca'
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
