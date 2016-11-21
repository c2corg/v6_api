import transaction
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class InitFeed(MigrateBase):
    """Initialize table `feed_document_changes` with the existing documents.
    """

    def migrate(self):
        self.start('feed')

        with transaction.manager:
            self.session_target.execute(SQL_DOCUMENT_CREATE_CHANGE)
            self.session_target.execute(SQL_AREAS_FOR_CHANGES)
            self.session_target.execute(SQL_ACTIVITIES_FOR_CHANGES)
            self.session_target.execute(SQL_CREATION_USER)
            self.session_target.execute(SQL_OUTING_PARTICIPANTS)
            zope.sqlalchemy.mark_changed(self.session_target)

        # run vacuum on the table (must be outside a transaction)
        engine = self.session_target.bind
        conn = engine.connect()
        old_lvl = conn.connection.isolation_level
        conn.connection.set_isolation_level(0)
        conn.execute('vacuum analyze guidebook.feed_document_changes;')
        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()


# create a change for each document creation (not for image or user documents)
SQL_DOCUMENT_CREATE_CHANGE = """
with versions_of_documents as (
  select document_id,
         history_metadata_id,
         ROW_NUMBER() over(
           partition by document_id order by history_metadata_id) as i
  from guidebook.documents_versions
), first_version_of_documents as (
  select document_id, history_metadata_id
  from versions_of_documents
  where i = 1
), changes_for_documents as (
  select v.document_id, d.type, h.user_id, h.written_at
  from first_version_of_documents v
    join guidebook.history_metadata h on v.history_metadata_id = h.id
    join guidebook.documents d on v.document_id = d.document_id
)
insert into guidebook.feed_document_changes
  ("time", user_id, change_type, document_id, document_type)
  select written_at, user_id, 'created', document_id, type
  from changes_for_documents
  where type not in ('i', 'u') and user_id != 2;
"""


# set areas for document changes
SQL_AREAS_FOR_CHANGES = """
with areas_for_documents as (
  select c.change_id, array_agg(aa.area_id) area_ids
  from guidebook.feed_document_changes c join guidebook.area_associations aa
    on c.document_id = aa.document_id
  group by c.change_id
)
update guidebook.feed_document_changes as c
set area_ids = ac.area_ids
from areas_for_documents ac
where ac.change_id = c.change_id;
"""


# set activities for outings and routes
SQL_ACTIVITIES_FOR_CHANGES = """
with activities_for_outings as (
  select c.change_id, o.activities
  from guidebook.feed_document_changes c join guidebook.outings o
    on c.document_id = o.document_id
), activities_for_routes as (
  select c.change_id, r.activities
  from guidebook.feed_document_changes c join guidebook.routes r
    on c.document_id = r.document_id
), activities_for_routes_outings as (
  select change_id, activities
  from activities_for_outings union (select change_id, activities
  from activities_for_routes)
)
update guidebook.feed_document_changes as c
set activities = ac.activities
from activities_for_routes_outings ac
where ac.change_id = c.change_id;
"""


# set creator as user for all document types
SQL_CREATION_USER = """
update guidebook.feed_document_changes as c
set user_ids = ARRAY[c.user_id];
"""


# add participants to `user_ids` for outings
SQL_OUTING_PARTICIPANTS = """
with users_for_outings as (
  select c.change_id, array_agg(parent_document_id) user_ids
  from guidebook.feed_document_changes c join guidebook.associations a
    on c.document_id = a.child_document_id and
       c.document_type = 'o' and a.parent_document_type = 'u'
  group by c.change_id
)
update guidebook.feed_document_changes as c
set user_ids = ARRAY(
  SELECT DISTINCT UNNEST(array_cat(c.user_ids, uo.user_ids)) ORDER BY 1)
from users_for_outings uo
where uo.change_id = c.change_id;
"""
