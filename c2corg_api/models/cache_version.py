from c2corg_api.models import Base, schema, DBSession
from c2corg_api.models.document import Document
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import Integer
from sqlalchemy import event, DDL, text


class CacheVersion(Base):
    """This table contains a version number for each document that reflects
    the state of the document and all its associated documents.
    When the document or one of its associated documents is updated, the
    version of the document is incremented, so that outdated documents are not
    served from the cache.
    """
    __tablename__ = 'cache_versions'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        primary_key=True)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id
    )

    version = Column(Integer, nullable=False, server_default='1')


# Trigger that creates a new entry in the `CacheVersion` table when a new
# document is created.
trigger_ddl = DDL("""
CREATE OR REPLACE FUNCTION guidebook.create_cache_version() RETURNS TRIGGER AS
$BODY$
BEGIN
    INSERT INTO
        guidebook.cache_versions(document_id)
        VALUES(new.document_id);
    RETURN null;
END;
$BODY$
language plpgsql;

CREATE TRIGGER guidebook_documents_insert
AFTER INSERT ON guidebook.documents
FOR EACH ROW
EXECUTE PROCEDURE guidebook.create_cache_version();
""")
event.listen(Document.__table__, 'after_create', trigger_ddl)


# Function to update all dependent documents if a document changes
update_cache_version_ddl = DDL("""
CREATE OR REPLACE FUNCTION guidebook.update_cache_version(p_document_id integer, p_document_type character varying(1)) --  # noqa: E501
  RETURNS void AS
$BODY$
BEGIN
  -- update the version of the document itself
  UPDATE guidebook.cache_versions v SET version = version + 1
  WHERE v.document_id = p_document_id;

  -- update the version of linked documents (direct associations)
  PERFORM guidebook.update_cache_version_of_linked_documents(p_document_id);

  if p_document_type = 'w' then
    -- if the document is a waypoint, routes that this waypoint is
    -- main-waypoint of have to be updated.
    PERFORM guidebook.update_cache_version_of_main_waypoint_routes(p_document_id); --  # noqa: E501
  elsif p_document_type = 'r' then
     -- if the document is a route, associated waypoints (and their parent and
     -- grand-parents) have to be updated
    PERFORM guidebook.update_cache_version_of_route(p_document_id);
  elsif p_document_type = 'o' then
     -- if the document is an outing, associated waypoints of associates routes
     -- (and their parent and grand-parent waypoints) have to be updated
    PERFORM guidebook.update_cache_version_of_outing(p_document_id);
  end if;
END;
$BODY$
language plpgsql;


CREATE OR REPLACE FUNCTION guidebook.update_cache_version_of_linked_documents(p_document_id integer) --  # noqa: E501
  RETURNS void AS
$BODY$
BEGIN
  with v as (
    select a.parent_document_id as document_id
      from guidebook.associations a
      where a.child_document_id = p_document_id
    union (select b.child_document_id as document_id
      from guidebook.associations b
      where b.parent_document_id = p_document_id)
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.document_id;
END;
$BODY$
language plpgsql;


CREATE OR REPLACE FUNCTION guidebook.get_waypoints_for_routes(p_route_ids int[]) --  # noqa: E501
  RETURNS TABLE (waypoint_id int) AS
$BODY$
BEGIN
  -- given an array of route ids, return all linked waypoints, parent waypoints
  -- of these waypoints and the grand-parents of these waypoints
  RETURN QUERY with routes as (
    select route_id from unnest(p_route_ids) as route_id ),
  linked_waypoints as (
    select a.parent_document_id as t_waypoint_id
    from routes r join guidebook.associations a
    on r.route_id = a.child_document_id and a.parent_document_type = 'w'),
  waypoint_parents as (
    select a.parent_document_id as t_waypoint_id
    from linked_waypoints w join guidebook.associations a
    on a.child_document_id = w.t_waypoint_id and a.parent_document_type = 'w'),
  waypoint_grandparents as (
    select a.parent_document_id as t_waypoint_id
    from waypoint_parents w join guidebook.associations a
    on a.child_document_id = w.t_waypoint_id and a.parent_document_type = 'w')
  select t_waypoint_id as waypoint_id
    from linked_waypoints
    union select t_waypoint_id from waypoint_parents
    union select t_waypoint_id from waypoint_grandparents;
END;
$BODY$
language plpgsql;


CREATE OR REPLACE FUNCTION guidebook.update_cache_version_of_main_waypoint_routes(p_waypoint_id integer) --  # noqa: E501
  RETURNS void AS
$BODY$
BEGIN
  with v as (
    select guidebook.get_waypoints_for_routes(array_agg(document_id)) as waypoint_id --  # noqa: E501
    from guidebook.routes
    where main_waypoint_id = p_waypoint_id
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.waypoint_id;
END;
$BODY$
language plpgsql;


CREATE OR REPLACE FUNCTION guidebook.update_cache_version_of_route(p_route_id integer) --   # noqa: E501
  RETURNS void AS
$BODY$
BEGIN
  with v as (
    select guidebook.get_waypoints_for_routes(ARRAY[p_route_id]) as waypoint_id
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.waypoint_id;
END;
$BODY$
language plpgsql;


CREATE OR REPLACE FUNCTION guidebook.update_cache_version_of_outing(p_outing_id integer) --   # noqa: E501
  RETURNS void AS
$BODY$
BEGIN
  with v as (
    select guidebook.get_waypoints_for_routes(array_agg(a.parent_document_id)) as waypoint_id --   # noqa: E501
    from guidebook.associations a
    where a.child_document_id = p_outing_id and a.parent_document_type = 'r'
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.waypoint_id;
END;
$BODY$
language plpgsql;
""")
event.listen(CacheVersion.__table__, 'after_create', update_cache_version_ddl)


def update_cache_version(document):
    # TODO check for areas/map
    DBSession.execute(
        text('SELECT guidebook.update_cache_version(:document_id, :type)'),
        {'document_id': document.document_id, 'type': document.type}
    )
