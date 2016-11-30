"""Init

Initial version after the migration of the v5 database.

Revision ID: 38df9393c9a9
Revises: 
Create Date: 2016-11-30 13:59:10.855211

"""
from alembic import op
import sqlalchemy as sa
from c2corg_api.models import utils
from alembic_migration import extensions
from alembic_migration.extensions import drop_enum
import geoalchemy2
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.sqltypes import Enum

# revision identifiers, used by Alembic.
revision = '38df9393c9a9'
down_revision = None
branch_labels = None
depends_on = None


# trigger function that updates the field `last_updated` when a version is
# updated.
function_update_cache_version_time = extensions.ReplaceableObject(
    'guidebook.update_cache_version_time()',
    """
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = now();
    RETURN NEW;
END;
$$ language plpgsql;
""")


# trigger functions that creates a new entry in the `CacheVersion` table when a
# new document is created.
function_create_cache_version = extensions.ReplaceableObject(
    'guidebook.create_cache_version()',
    """
RETURNS TRIGGER AS
$BODY$
BEGIN
    INSERT INTO
        guidebook.cache_versions(document_id)
        VALUES(new.document_id);
    RETURN null;
END;
$BODY$
language plpgsql;
""")


# functions to update the cache version if a document or associations
# have changed
function_update_cache_version = extensions.ReplaceableObject(
    'guidebook.update_cache_version(p_document_id integer, p_document_type character varying(1))',
    """
RETURNS void AS
$BODY$
BEGIN
  -- function to update all dependent documents if a document changes

  -- update the version of the document itself
  PERFORM guidebook.increment_cache_version(p_document_id);

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
  elsif p_document_type = 'u' then
     -- if the document is an user profile, all documents that this user has
     -- edited have to be updated (to refresh the user name)
    PERFORM guidebook.update_cache_version_for_user(p_document_id);
  end if;
END;
$BODY$
language plpgsql;
""")


function_increment_cache_version = extensions.ReplaceableObject(
    'guidebook.increment_cache_version(p_document_id integer)',
    """
RETURNS void AS
$BODY$
BEGIN
  UPDATE guidebook.cache_versions v SET version = version + 1
  WHERE v.document_id = p_document_id;
END;
$BODY$
language plpgsql;
""")


function_increment_cache_versions = extensions.ReplaceableObject(
    'guidebook.increment_cache_versions(p_document_ids integer[])',
    """
RETURNS void AS
$BODY$
BEGIN
  PERFORM guidebook.increment_cache_version(document_id)
  from unnest(p_document_ids) as document_id;
END;
$BODY$
language plpgsql;
""")


function_update_cache_version_of_linked_documents = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_linked_documents(p_document_id integer)',
    """
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
""")


function_get_waypoints_for_routes = extensions.ReplaceableObject(
    'guidebook.get_waypoints_for_routes(p_route_ids int[])',
    """
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
""")


function_update_cache_version_of_main_waypoint_routes = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_main_waypoint_routes(p_waypoint_id integer)',
    """
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
""")


function_update_cache_version_of_route = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_route(p_route_id integer)',
    """
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
""")


function_update_cache_version_of_routes = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_routes(p_route_ids integer[])',
    """
RETURNS void AS
$BODY$
BEGIN
  -- update the cache versions of waypoints (and the parent and grand-parent
  -- waypoints) associated to the given routes.
  PERFORM guidebook.update_cache_version_of_route(route_id)
  from unnest(p_route_ids) as route_id;
END;
$BODY$
language plpgsql;
""")


function_update_cache_version_of_waypoints = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_waypoints(p_waypoints_ids integer[])',
    """
RETURNS void AS
$BODY$
BEGIN
  -- update the cache versions of the parent and grand-parent waypoints
  -- of the given waypoints.
  with waypoints as (
    select waypoint_id from unnest(p_waypoints_ids) as waypoint_id ),
  waypoint_parents as (
    select a.parent_document_id as waypoint_id
    from waypoints w join guidebook.associations a
    on a.child_document_id = w.waypoint_id and a.parent_document_type = 'w'),
  waypoint_grandparents as (
    select a.parent_document_id as waypoint_id
    from waypoint_parents w join guidebook.associations a
    on a.child_document_id = w.waypoint_id and a.parent_document_type = 'w'),
  v as (
    select waypoint_id
    from waypoint_parents
    union select waypoint_id from waypoint_grandparents)
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.waypoint_id;
END;
$BODY$
language plpgsql;
""")


function_update_cache_version_of_outing = extensions.ReplaceableObject(
    'guidebook.update_cache_version_of_outing(p_outing_id integer)',
    """
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


function_update_cache_version_for_user = extensions.ReplaceableObject(
    'guidebook.update_cache_version_for_user(p_user_id integer)',
    """
RETURNS void AS
$BODY$
BEGIN
  -- function to update all documents that the given user edited
  with v as (
    select dv.document_id as document_id
    from guidebook.documents_versions dv
      inner join guidebook.history_metadata h
    on dv.history_metadata_id = h.id
    where h.user_id = p_user_id
    group by dv.document_id
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.document_id;
END;
$BODY$
language plpgsql;
""")


function_update_cache_version_for_area = extensions.ReplaceableObject(
    'guidebook.update_cache_version_for_area(p_area_id integer)',
    """
RETURNS void AS
$BODY$
BEGIN
  -- function to update all documents that are associated with the given area
  with v as (
    select aa.document_id as document_id
    from guidebook.area_associations aa
    where aa.area_id = p_area_id
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.document_id;
END;
$BODY$
language plpgsql;
""")


function_update_cache_version_for_map = extensions.ReplaceableObject(
    'guidebook.update_cache_version_for_map(p_map_id integer)',
    """
RETURNS void AS
$BODY$
BEGIN
  -- function to update all documents that are associated with the given map
  with v as (
    select ma.document_id as document_id
    from guidebook.map_associations ma
    where ma.topo_map_id = p_map_id
  )
  update guidebook.cache_versions cv SET version = version + 1
  from v
  where cv.document_id = v.document_id;
END;
$BODY$
language plpgsql;
""")


function_simplify_geom_detail = extensions.ReplaceableObject(
    'guidebook.simplify_geom_detail()',
    """
RETURNS TRIGGER AS
$BODY$
DECLARE
  document_type varchar;
BEGIN
  IF new.geom_detail is not null THEN
    SELECT type from guidebook.documents where document_id = new.document_id
        INTO STRICT document_type;
    IF document_type in ('r', 'o') THEN
      new.geom_detail := ST_Simplify(new.geom_detail, 5);
    END IF;
  END IF;
  RETURN new;
END;
$BODY$
language plpgsql;
""")


# For performance reasons, areas and users are referenced in simple integer
# arrays in 'feed_document_changes', no PK-FK relations are set up. To prevent
# inconsistencies, triggers are used.

# when creating a change, check that the given user and area ids are valid
function_check_feed_ids = extensions.ReplaceableObject(
    'guidebook.check_feed_ids()',
    """
RETURNS TRIGGER AS
$BODY$
DECLARE
  user_id int;
  area_id int;
BEGIN
  -- check user ids
  FOREACH user_id IN ARRAY new.user_ids LOOP
    PERFORM id from users.user where id = user_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Invalid user id: %', user_id;
    END IF;
  END LOOP;
  -- check area ids
  FOREACH area_id IN ARRAY new.area_ids LOOP
    PERFORM document_id from guidebook.areas where document_id = area_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Invalid area id: %', area_id;
    END IF;
  END LOOP;
  RETURN null;
END;
$BODY$
language plpgsql;
""")

# when deleting a user, check that there are no changes referencing the user
function_check_feed_user_ids = extensions.ReplaceableObject(
    'guidebook.check_feed_user_ids()',
    """
RETURNS TRIGGER AS
$BODY$
BEGIN
  -- check user ids
  PERFORM change_id from guidebook.feed_document_changes
    where user_ids @> ARRAY[OLD.id] limit 1;
  IF FOUND THEN
    RAISE EXCEPTION 'Row in feed_document_changes still references user id %', OLD.id;
  END IF;
  RETURN null;
END;
$BODY$
language plpgsql;
""")

# when deleting an area, check that there are no changes referencing the area
function_check_feed_area_ids = extensions.ReplaceableObject(
    'guidebook.check_feed_area_ids()',
    """
RETURNS TRIGGER AS
$BODY$
BEGIN
  -- check area ids
  PERFORM change_id from guidebook.feed_document_changes
    where area_ids @> ARRAY[OLD.document_id] limit 1;
  IF FOUND THEN
    RAISE EXCEPTION 'Row in feed_document_changes still references area id %', OLD.document_id;
  END IF;
  RETURN null;
END;
$BODY$
language plpgsql;
""")

# Check forum_username validity with discourse
# https://github.com/discourse/discourse/blob/master/app/models/username_validator.rb
function_check_forum_username = extensions.ReplaceableObject(
    'users.check_forum_username(name TEXT)',
    """
RETURNS boolean AS $$
BEGIN
  IF name = NULL THEN
    RETURN FALSE;
  END IF;

  IF char_length(name) < 3 THEN
    RETURN FALSE;
  END IF;

  IF char_length(name) > 25 THEN
    RETURN FALSE;
  END IF;

  if name ~ '[^\w.-]' THEN
    RETURN FALSE;
  END IF;

  if left(name, 1) ~ '\W' THEN
    RETURN FALSE;
  END IF;

  if right(name, 1) ~ '[^A-Za-z0-9]' THEN
    RETURN FALSE;
  END IF;

  if name ~ '[-_\.]{2,}' THEN
    RETURN FALSE;
  END IF;

  if name ~
  '\.(js|json|css|htm|html|xml|jpg|jpeg|png|gif|bmp|ico|tif|tiff|woff)$'
  THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;
""")


# make sure that user email changes are propagated to mailing lists as well
function_update_mailinglists_email = extensions.ReplaceableObject(
    'users.update_mailinglists_email()',
    """
RETURNS TRIGGER AS
$BODY$
BEGIN
  UPDATE sympa.subscriber_table
  SET user_subscriber = NEW.email
  WHERE user_subscriber = OLD.email;
  RETURN null;
END;
$BODY$
language plpgsql;
""")


# Views
view_waypoints_for_routes = extensions.ReplaceableObject(
    'guidebook.waypoints_for_routes',
    """
WITH linked_waypoints AS
  (SELECT guidebook.associations.child_document_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM guidebook.associations
   WHERE guidebook.associations.parent_document_type = 'w'
     AND guidebook.associations.child_document_type = 'r'),
     waypoint_parents AS
  (SELECT linked_waypoints.route_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM linked_waypoints
   JOIN guidebook.associations ON guidebook.associations.child_document_id = linked_waypoints.waypoint_id
   AND guidebook.associations.parent_document_type = 'w'),
     waypoint_grandparents AS
  (SELECT waypoint_parents.route_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM waypoint_parents
   JOIN guidebook.associations ON guidebook.associations.child_document_id = waypoint_parents.waypoint_id
   AND guidebook.associations.parent_document_type = 'w'),
     all_waypoints AS
  (SELECT linked_waypoints.route_id AS route_id,
          linked_waypoints.waypoint_id AS waypoint_id
   FROM linked_waypoints
   UNION SELECT waypoint_parents.route_id AS route_id,
                waypoint_parents.waypoint_id AS waypoint_id
   FROM waypoint_parents
   UNION SELECT waypoint_grandparents.route_id AS route_id,
                waypoint_grandparents.waypoint_id AS waypoint_id
   FROM waypoint_grandparents)
SELECT all_waypoints.route_id AS route_id,
       array_agg(all_waypoints.waypoint_id) AS waypoint_ids
FROM all_waypoints
GROUP BY all_waypoints.route_id;
""")

view_waypoints_for_outings = extensions.ReplaceableObject(
    'guidebook.waypoints_for_outings',
    """
WITH linked_waypoints AS
  (SELECT guidebook.associations.child_document_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM guidebook.associations
   WHERE guidebook.associations.parent_document_type = 'w'
     AND guidebook.associations.child_document_type = 'r'),
     waypoint_parents AS
  (SELECT linked_waypoints.route_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM linked_waypoints
   JOIN guidebook.associations ON guidebook.associations.child_document_id = linked_waypoints.waypoint_id
   AND guidebook.associations.parent_document_type = 'w'),
     waypoint_grandparents AS
  (SELECT waypoint_parents.route_id AS route_id,
          guidebook.associations.parent_document_id AS waypoint_id
   FROM waypoint_parents
   JOIN guidebook.associations ON guidebook.associations.child_document_id = waypoint_parents.waypoint_id
   AND guidebook.associations.parent_document_type = 'w'),
     all_waypoints AS
  (SELECT linked_waypoints.route_id AS route_id,
          linked_waypoints.waypoint_id AS waypoint_id
   FROM linked_waypoints
   UNION SELECT waypoint_parents.route_id AS route_id,
                waypoint_parents.waypoint_id AS waypoint_id
   FROM waypoint_parents
   UNION SELECT waypoint_grandparents.route_id AS route_id,
                waypoint_grandparents.waypoint_id AS waypoint_id
   FROM waypoint_grandparents),
     waypoints_for_outings AS
  (SELECT guidebook.associations.child_document_id AS outing_id,
          all_waypoints.waypoint_id AS waypoint_id
   FROM guidebook.associations
   JOIN all_waypoints ON guidebook.associations.parent_document_id = all_waypoints.route_id
   AND guidebook.associations.parent_document_type = 'r'
   AND guidebook.associations.child_document_type = 'o')
SELECT waypoints_for_outings.outing_id AS outing_id,
       array_agg(waypoints_for_outings.waypoint_id) AS waypoint_ids
FROM waypoints_for_outings
GROUP BY waypoints_for_outings.outing_id;
""")

view_users_for_outings = extensions.ReplaceableObject(
    'guidebook.users_for_outings',
    """
SELECT guidebook.associations.child_document_id AS outing_id, array_agg(guidebook.associations.parent_document_id) AS user_ids
FROM guidebook.associations
WHERE guidebook.associations.parent_document_type = 'u' AND guidebook.associations.child_document_type = 'o' GROUP BY guidebook.associations.child_document_id;
""")

view_routes_for_outings = extensions.ReplaceableObject(
    'guidebook.routes_for_outings',
    """
SELECT guidebook.associations.child_document_id AS outing_id, array_agg(guidebook.associations.parent_document_id) AS route_ids
FROM guidebook.associations
WHERE guidebook.associations.parent_document_type = 'r' AND guidebook.associations.child_document_type = 'o' GROUP BY guidebook.associations.child_document_id;
""")


def upgrade():
    # ### commands auto generated by Alembic ###
    op.create_table('documents',
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('protected', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('quality', sa.Enum('empty', 'draft', 'medium', 'fine', 'great', name='quality_type', schema='guidebook'), server_default='draft', nullable=False),
    sa.Column('type', sa.String(length=1), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('redirects_to', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['redirects_to'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_documents_type'), 'documents', ['type'], unique=False, schema='guidebook')
    op.create_table('es_sync_status',
    sa.Column('last_update', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.CheckConstraint('id = 1', name='one_row_constraint'),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('langs',
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.PrimaryKeyConstraint('lang'),
    schema='guidebook'
    )
    op.create_table('areas',
    sa.Column('area_type', sa.Enum('range', 'admin_limits', 'country', name='area_type', schema='guidebook'), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('articles',
    sa.Column('categories', utils.ArrayOfEnum(Enum('mountain_environment', 'gear', 'technical', 'topoguide_supplements', 'soft_mobility', 'expeditions', 'stories', 'c2c_meetings', 'tags', 'site_info', 'association', name='article_category', schema='guidebook')), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('article_type', sa.Enum('collab', 'personal', name='article_type', schema='guidebook'), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('associations',
    sa.Column('parent_document_id', sa.Integer(), nullable=False),
    sa.Column('parent_document_type', sa.String(length=1), nullable=False),
    sa.Column('child_document_id', sa.Integer(), nullable=False),
    sa.Column('child_document_type', sa.String(length=1), nullable=False),
    sa.ForeignKeyConstraint(['child_document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['parent_document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('parent_document_id', 'child_document_id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_associations_child_document_id'), 'associations', ['child_document_id'], unique=False, schema='guidebook')
    op.create_index(op.f('ix_guidebook_associations_child_document_type'), 'associations', ['child_document_type'], unique=False, schema='guidebook')
    op.create_index(op.f('ix_guidebook_associations_parent_document_id'), 'associations', ['parent_document_id'], unique=False, schema='guidebook')
    op.create_index(op.f('ix_guidebook_associations_parent_document_type'), 'associations', ['parent_document_type'], unique=False, schema='guidebook')
    op.create_table('books',
    sa.Column('author', sa.String(length=100), nullable=True),
    sa.Column('editor', sa.String(length=100), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('url', sa.String(length=255), nullable=True),
    sa.Column('isbn', sa.String(length=17), nullable=True),
    sa.Column('book_types', utils.ArrayOfEnum(Enum('topo', 'environment', 'historical', 'biography', 'photos-art', 'novel', 'technics', 'tourism', 'magazine', name='book_type', schema='guidebook')), nullable=True),
    sa.Column('nb_pages', sa.SmallInteger(), nullable=True),
    sa.Column('publication_date', sa.String(length=100), nullable=True),
    sa.Column('langs', postgresql.ARRAY(sa.String(length=2)), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('cache_versions',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('last_updated', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('documents_archives',
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('protected', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('quality', sa.Enum('empty', 'draft', 'medium', 'fine', 'great', name='quality_type', schema='guidebook'), server_default='draft', nullable=False),
    sa.Column('type', sa.String(length=1), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('redirects_to', sa.Integer(), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['redirects_to'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'document_id', name='uq_documents_archives_document_id_version'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_documents_archives_type'), 'documents_archives', ['type'], unique=False, schema='guidebook')
    op.create_table('documents_geometries',
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=3857, management=True), nullable=True),
    sa.Column('geom_detail', geoalchemy2.types.Geometry(srid=3857, management=True, use_typmod=False), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('documents_geometries_archives',
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=3857, spatial_index=False, management=True), nullable=True),
    sa.Column('geom_detail', geoalchemy2.types.Geometry(srid=3857, spatial_index=False, management=True, use_typmod=False), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'document_id', name='uq_documents_geometries_archives_document_id_version_lang'),
    schema='guidebook'
    )
    op.create_table('documents_locales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('summary', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('type', sa.String(length=1), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_documents_locales_document_id'), 'documents_locales', ['document_id'], unique=False, schema='guidebook')
    op.create_table('documents_locales_archives',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('summary', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('type', sa.String(length=1), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'document_id', 'lang', name='uq_documents_locales_archives_document_id_version_lang'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_documents_locales_archives_document_id'), 'documents_locales_archives', ['document_id'], unique=False, schema='guidebook')
    op.create_table('images',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('categories', utils.ArrayOfEnum(Enum('landscapes', 'detail', 'action', 'track', 'rise', 'descent', 'topo', 'people', 'fauna', 'flora', 'nivology', 'geology', 'hut', 'equipment', 'book', 'help', 'misc', name='image_category', schema='guidebook')), nullable=True),
    sa.Column('image_type', sa.Enum('collaborative', 'personal', 'copyright', name='image_type', schema='guidebook'), nullable=True),
    sa.Column('author', sa.String(length=100), nullable=True),
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('height', sa.SmallInteger(), nullable=True),
    sa.Column('width', sa.SmallInteger(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('filename', sa.String(length=30), nullable=False),
    sa.Column('date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('camera_name', sa.String(length=100), nullable=True),
    sa.Column('exposure_time', sa.Float(), nullable=True),
    sa.Column('focal_length', sa.Float(), nullable=True),
    sa.Column('fnumber', sa.Float(), nullable=True),
    sa.Column('iso_speed', sa.SmallInteger(), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('maps',
    sa.Column('editor', sa.Enum('IGN', 'Swisstopo', 'Escursionista', name='map_editor', schema='guidebook'), nullable=True),
    sa.Column('scale', sa.Enum('25000', '50000', '100000', name='map_scale', schema='guidebook'), nullable=True),
    sa.Column('code', sa.String(), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('outings',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.Column('frequentation', sa.Enum('quiet', 'some', 'crowded', 'overcrowded', name='frequentation_type', schema='guidebook'), nullable=True),
    sa.Column('participant_count', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_max', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_access', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_up_snow', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_down_snow', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_up', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_down', sa.SmallInteger(), nullable=True),
    sa.Column('length_total', sa.Integer(), nullable=True),
    sa.Column('partial_trip', sa.Boolean(), nullable=True),
    sa.Column('public_transport', sa.Boolean(), nullable=True),
    sa.Column('access_condition', sa.Enum('cleared', 'snowy', 'closed_snow', 'closed_cleared', name='access_condition', schema='guidebook'), nullable=True),
    sa.Column('lift_status', sa.Enum('open', 'closed', name='lift_status', schema='guidebook'), nullable=True),
    sa.Column('condition_rating', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_quantity', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_quality', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('glacier_rating', sa.Enum('easy', 'possible', 'difficult', 'impossible', name='glacier_rating', schema='guidebook'), nullable=True),
    sa.Column('avalanche_signs', utils.ArrayOfEnum(Enum('no', 'danger_sign', 'recent_avalanche', 'natural_avalanche', 'accidental_avalanche', name='avalanche_signs', schema='guidebook')), nullable=True),
    sa.Column('hut_status', sa.Enum('open_guarded', 'open_non_guarded', 'closed_hut', name='hut_status', schema='guidebook'), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('routes',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_max', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_up', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_down', sa.SmallInteger(), nullable=True),
    sa.Column('route_length', sa.Integer(), nullable=True),
    sa.Column('difficulties_height', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_access', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_difficulties', sa.SmallInteger(), nullable=True),
    sa.Column('route_types', utils.ArrayOfEnum(Enum('return_same_way', 'loop', 'loop_hut', 'traverse', 'raid', 'expedition', name='route_type', schema='guidebook')), nullable=True),
    sa.Column('orientations', utils.ArrayOfEnum(Enum('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', name='orientation_type', schema='guidebook')), nullable=True),
    sa.Column('durations', utils.ArrayOfEnum(Enum('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '10+', name='route_duration_type', schema='guidebook')), nullable=True),
    sa.Column('glacier_gear', sa.Enum('no', 'glacier_safety_gear', 'crampons_spring', 'crampons_req', 'glacier_crampons', name='glacier_gear_type', schema='guidebook'), server_default='no', nullable=False),
    sa.Column('configuration', utils.ArrayOfEnum(Enum('edge', 'pillar', 'face', 'corridor', 'goulotte', 'glacier', name='route_configuration_type', schema='guidebook')), nullable=True),
    sa.Column('lift_access', sa.Boolean(), nullable=True),
    sa.Column('ski_rating', sa.Enum('1.1', '1.2', '1.3', '2.1', '2.2', '2.3', '3.1', '3.2', '3.3', '4.1', '4.2', '4.3', '5.1', '5.2', '5.3', '5.4', '5.5', '5.6', name='ski_rating', schema='guidebook'), nullable=True),
    sa.Column('ski_exposition', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('labande_ski_rating', sa.Enum('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', name='labande_ski_rating', schema='guidebook'), nullable=True),
    sa.Column('labande_global_rating', sa.Enum('F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+', 'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED', 'ED+', 'ED4', 'ED5', 'ED6', 'ED7', name='global_rating', schema='guidebook'), nullable=True),
    sa.Column('global_rating', sa.Enum('F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+', 'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED', 'ED+', 'ED4', 'ED5', 'ED6', 'ED7', name='global_rating', schema='guidebook'), nullable=True),
    sa.Column('engagement_rating', sa.Enum('I', 'II', 'III', 'IV', 'V', 'VI', name='engagement_rating', schema='guidebook'), nullable=True),
    sa.Column('risk_rating', sa.Enum('X1', 'X2', 'X3', 'X4', 'X5', name='risk_rating', schema='guidebook'), nullable=True),
    sa.Column('equipment_rating', sa.Enum('P1', 'P1+', 'P2', 'P2+', 'P3', 'P3+', 'P4', 'P4+', name='equipment_rating', schema='guidebook'), nullable=True),
    sa.Column('ice_rating', sa.Enum('1', '2', '3', '3+', '4', '4+', '5', '5+', '6', '6+', '7', '7+', name='ice_rating', schema='guidebook'), nullable=True),
    sa.Column('mixed_rating', sa.Enum('M1', 'M2', 'M3', 'M3+', 'M4', 'M4+', 'M5', 'M5+', 'M6', 'M6+', 'M7', 'M7+', 'M8', 'M8+', 'M9', 'M9+', 'M10', 'M10+', 'M11', 'M11+', 'M12', 'M12+', name='mixed_rating', schema='guidebook'), nullable=True),
    sa.Column('exposition_rock_rating', sa.Enum('E1', 'E2', 'E3', 'E4', 'E5', 'E6', name='exposition_rock_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_free_rating', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_required_rating', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('aid_rating', sa.Enum('A0', 'A0+', 'A1', 'A1+', 'A2', 'A2+', 'A3', 'A3+', 'A4', 'A4+', 'A5', 'A5+', name='aid_rating', schema='guidebook'), nullable=True),
    sa.Column('via_ferrata_rating', sa.Enum('K1', 'K2', 'K3', 'K4', 'K5', 'K6', name='via_ferrata_rating', schema='guidebook'), nullable=True),
    sa.Column('hiking_rating', sa.Enum('T1', 'T2', 'T3', 'T4', 'T5', name='hiking_rating', schema='guidebook'), nullable=True),
    sa.Column('hiking_mtb_exposition', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('snowshoe_rating', sa.Enum('R1', 'R2', 'R3', 'R4', 'R5', name='snowshoe_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_up_rating', sa.Enum('M1', 'M2', 'M3', 'M4', 'M5', name='mtb_up_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_down_rating', sa.Enum('V1', 'V2', 'V3', 'V4', 'V5', name='mtb_down_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_length_asphalt', sa.Integer(), nullable=True),
    sa.Column('mtb_length_trail', sa.Integer(), nullable=True),
    sa.Column('mtb_height_diff_portages', sa.Integer(), nullable=True),
    sa.Column('rock_types', utils.ArrayOfEnum(Enum('basalte', 'calcaire', 'conglomerat', 'craie', 'gneiss', 'gres', 'granit', 'migmatite', 'mollasse_calcaire', 'pouding', 'quartzite', 'rhyolite', 'schiste', 'trachyte', 'artificial', name='rock_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_outdoor_type', sa.Enum('single', 'multi', 'bloc', 'psicobloc', name='climbing_outdoor_type', schema='guidebook'), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('main_waypoint_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['main_waypoint_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_routes_main_waypoint_id'), 'routes', ['main_waypoint_id'], unique=False, schema='guidebook')
    op.create_table('user_profiles',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('categories', utils.ArrayOfEnum(Enum('amateur', 'mountain_guide', 'mountain_leader', 'ski_instructor', 'climbing_instructor', 'mountainbike_instructor', 'paragliding_instructor', 'hut_warden', 'ski_patroller', 'avalanche_forecaster', 'club', 'institution', name='user_category', schema='guidebook')), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('waypoints',
    sa.Column('waypoint_type', sa.Enum('summit', 'pass', 'lake', 'waterfall', 'locality', 'bisse', 'canyon', 'access', 'climbing_outdoor', 'climbing_indoor', 'hut', 'gite', 'shelter', 'bivouac', 'camp_site', 'base_camp', 'local_product', 'paragliding_takeoff', 'paragliding_landing', 'cave', 'waterpoint', 'weather_station', 'webcam', 'virtual', 'misc', name='waypoint_type', schema='guidebook'), nullable=False),
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('prominence', sa.SmallInteger(), nullable=True),
    sa.Column('height_max', sa.SmallInteger(), nullable=True),
    sa.Column('height_median', sa.SmallInteger(), nullable=True),
    sa.Column('height_min', sa.SmallInteger(), nullable=True),
    sa.Column('routes_quantity', sa.SmallInteger(), nullable=True),
    sa.Column('climbing_outdoor_types', utils.ArrayOfEnum(Enum('single', 'multi', 'bloc', 'psicobloc', name='climbing_outdoor_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_indoor_types', utils.ArrayOfEnum(Enum('pitch', 'bloc', name='climbing_indoor_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_rating_max', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('climbing_rating_min', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('climbing_rating_median', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('equipment_ratings', utils.ArrayOfEnum(Enum('P1', 'P1+', 'P2', 'P2+', 'P3', 'P3+', 'P4', 'P4+', name='equipment_rating', schema='guidebook')), nullable=True),
    sa.Column('climbing_styles', utils.ArrayOfEnum(Enum('slab', 'vertical', 'overhang', 'roof', 'small_pillar', 'crack_dihedral', name='climbing_style', schema='guidebook')), nullable=True),
    sa.Column('children_proof', sa.Enum('very_safe', 'safe', 'dangerous', 'very_dangerous', name='children_proof_type', schema='guidebook'), nullable=True),
    sa.Column('rain_proof', sa.Enum('exposed', 'partly_protected', 'protected', 'inside', name='rain_proof_type', schema='guidebook'), nullable=True),
    sa.Column('orientations', utils.ArrayOfEnum(Enum('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', name='orientation_type', schema='guidebook')), nullable=True),
    sa.Column('best_periods', utils.ArrayOfEnum(Enum('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec', name='month_type', schema='guidebook')), nullable=True),
    sa.Column('product_types', utils.ArrayOfEnum(Enum('farm_sale', 'restaurant', 'grocery', 'bar', 'sport_shop', name='product_type', schema='guidebook')), nullable=True),
    sa.Column('length', sa.SmallInteger(), nullable=True),
    sa.Column('slope', sa.SmallInteger(), nullable=True),
    sa.Column('ground_types', utils.ArrayOfEnum(Enum('prairie', 'scree', 'snow', name='ground_type', schema='guidebook')), nullable=True),
    sa.Column('paragliding_rating', sa.Enum('1', '2', '3', '4', '5', name='paragliding_rating', schema='guidebook'), nullable=True),
    sa.Column('exposition_rating', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_types', utils.ArrayOfEnum(Enum('basalte', 'calcaire', 'conglomerat', 'craie', 'gneiss', 'gres', 'granit', 'migmatite', 'mollasse_calcaire', 'pouding', 'quartzite', 'rhyolite', 'schiste', 'trachyte', 'artificial', name='rock_type', schema='guidebook')), nullable=True),
    sa.Column('weather_station_types', utils.ArrayOfEnum(Enum('temperature', 'wind_speed', 'wind_direction', 'humidity', 'pressure', 'precipitation', 'precipitation_heater', 'snow_height', 'insolation', name='weather_station_type', schema='guidebook')), nullable=True),
    sa.Column('url', sa.String(length=255), nullable=True),
    sa.Column('maps_info', sa.String(length=300), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('public_transportation_types', utils.ArrayOfEnum(Enum('train', 'bus', 'service_on_demand', 'boat', 'cable_car', name='public_transportation_type', schema='guidebook')), nullable=True),
    sa.Column('public_transportation_rating', sa.Enum('good service', 'seasonal service', 'poor service', 'nearby service', 'no service', name='public_transportation_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_clearance_rating', sa.Enum('often', 'sometimes', 'progressive', 'naturally', 'closed_in_winter', 'non_applicable', name='snow_clearance_rating', schema='guidebook'), nullable=True),
    sa.Column('lift_access', sa.Boolean(), nullable=True),
    sa.Column('parking_fee', sa.Enum('yes', 'seasonal', 'no', name='parking_fee_type', schema='guidebook'), nullable=True),
    sa.Column('phone_custodian', sa.String(length=50), nullable=True),
    sa.Column('custodianship', sa.Enum('accessible_when_wardened', 'always_accessible', 'key_needed', 'no_warden', name='custodianship_type', schema='guidebook'), nullable=True),
    sa.Column('matress_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('blanket_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('gas_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('heating_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('access_time', sa.Enum('1min', '5min', '10min', '15min', '20min', '30min', '45min', '1h', '1h30', '2h', '2h30', '3h', '3h+', name='access_time_type', schema='guidebook'), nullable=True),
    sa.Column('capacity', sa.SmallInteger(), nullable=True),
    sa.Column('capacity_staffed', sa.SmallInteger(), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('xreports',
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('event_type', utils.ArrayOfEnum(Enum('avalanche', 'stone_fall', 'falling_ice', 'person_fall', 'crevasse_fall', 'roped_fall', 'physical_failure', 'lightning', 'other', name='event_type', schema='guidebook')), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('nb_participants', sa.SmallInteger(), nullable=True),
    sa.Column('nb_impacted', sa.SmallInteger(), nullable=True),
    sa.Column('rescue', sa.Boolean(), nullable=True),
    sa.Column('avalanche_level', sa.Enum('level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'level_na', name='avalanche_level', schema='guidebook'), nullable=True),
    sa.Column('avalanche_slope', sa.Enum('slope_lt_30', 'slope_30_32', 'slope_33_35', 'slope_36_38', 'slope_39_41', 'slope_42_44', 'slope_45_47', 'slope_gt_47', name='avalanche_slope', schema='guidebook'), nullable=True),
    sa.Column('severity', sa.Enum('severity_no', '1d_to_3d', '4d_to_1m', '1m_to_3m', 'more_than_3m', name='severity', schema='guidebook'), nullable=True),
    sa.Column('author_status', sa.Enum('primary_impacted', 'secondary_impacted', 'internal_witness', 'external_witness', name='author_status', schema='guidebook'), nullable=True),
    sa.Column('activity_rate', sa.Enum('activity_rate_150', 'activity_rate_50', 'activity_rate_30', 'activity_rate_20', 'activity_rate_10', 'activity_rate_5', 'activity_rate_1', name='activity_rate', schema='guidebook'), nullable=True),
    sa.Column('nb_outings', sa.Enum('nb_outings_4', 'nb_outings_9', 'nb_outings_14', 'nb_outings_15', name='nb_outings', schema='guidebook'), nullable=True),
    sa.Column('age', sa.SmallInteger(), nullable=True),
    sa.Column('gender', sa.Enum('male', 'female', name='gender', schema='guidebook'), nullable=True),
    sa.Column('previous_injuries', sa.Enum('no', 'previous_injuries_2', 'previous_injuries_3', name='previous_injuries', schema='guidebook'), nullable=True),
    sa.Column('autonomy', sa.Enum('non_autonomous', 'autonomous', 'initiator', 'expert', name='autonomy', schema='guidebook'), nullable=True),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id'),
    schema='guidebook'
    )
    op.create_table('area_associations',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['guidebook.areas.document_id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('document_id', 'area_id'),
    schema='guidebook'
    )
    op.create_table('areas_archives',
    sa.Column('area_type', sa.Enum('range', 'admin_limits', 'country', name='area_type', schema='guidebook'), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('articles_archives',
    sa.Column('categories', utils.ArrayOfEnum(Enum('mountain_environment', 'gear', 'technical', 'topoguide_supplements', 'soft_mobility', 'expeditions', 'stories', 'c2c_meetings', 'tags', 'site_info', 'association', name='article_category', schema='guidebook')), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('article_type', sa.Enum('collab', 'personal', name='article_type', schema='guidebook'), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('books_archives',
    sa.Column('author', sa.String(length=100), nullable=True),
    sa.Column('editor', sa.String(length=100), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('url', sa.String(length=255), nullable=True),
    sa.Column('isbn', sa.String(length=17), nullable=True),
    sa.Column('book_types', utils.ArrayOfEnum(Enum('topo', 'environment', 'historical', 'biography', 'photos-art', 'novel', 'technics', 'tourism', 'magazine', name='book_type', schema='guidebook')), nullable=True),
    sa.Column('nb_pages', sa.SmallInteger(), nullable=True),
    sa.Column('publication_date', sa.String(length=100), nullable=True),
    sa.Column('langs', postgresql.ARRAY(sa.String(length=2)), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('documents_topics',
    sa.Column('document_locale_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_locale_id'], ['guidebook.documents_locales.id'], ),
    sa.PrimaryKeyConstraint('document_locale_id'),
    sa.UniqueConstraint('topic_id'),
    schema='guidebook'
    )
    op.create_table('images_archives',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('categories', utils.ArrayOfEnum(Enum('landscapes', 'detail', 'action', 'track', 'rise', 'descent', 'topo', 'people', 'fauna', 'flora', 'nivology', 'geology', 'hut', 'equipment', 'book', 'help', 'misc', name='image_category', schema='guidebook')), nullable=True),
    sa.Column('image_type', sa.Enum('collaborative', 'personal', 'copyright', name='image_type', schema='guidebook'), nullable=True),
    sa.Column('author', sa.String(length=100), nullable=True),
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('height', sa.SmallInteger(), nullable=True),
    sa.Column('width', sa.SmallInteger(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('filename', sa.String(length=30), nullable=False),
    sa.Column('date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('camera_name', sa.String(length=100), nullable=True),
    sa.Column('exposure_time', sa.Float(), nullable=True),
    sa.Column('focal_length', sa.Float(), nullable=True),
    sa.Column('fnumber', sa.Float(), nullable=True),
    sa.Column('iso_speed', sa.SmallInteger(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('map_associations',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('topo_map_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['topo_map_id'], ['guidebook.maps.document_id'], ),
    sa.PrimaryKeyConstraint('document_id', 'topo_map_id'),
    schema='guidebook'
    )
    op.create_table('maps_archives',
    sa.Column('editor', sa.Enum('IGN', 'Swisstopo', 'Escursionista', name='map_editor', schema='guidebook'), nullable=True),
    sa.Column('scale', sa.Enum('25000', '50000', '100000', name='map_scale', schema='guidebook'), nullable=True),
    sa.Column('code', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('outings_archives',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.Column('frequentation', sa.Enum('quiet', 'some', 'crowded', 'overcrowded', name='frequentation_type', schema='guidebook'), nullable=True),
    sa.Column('participant_count', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_max', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_access', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_up_snow', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_down_snow', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_up', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_down', sa.SmallInteger(), nullable=True),
    sa.Column('length_total', sa.Integer(), nullable=True),
    sa.Column('partial_trip', sa.Boolean(), nullable=True),
    sa.Column('public_transport', sa.Boolean(), nullable=True),
    sa.Column('access_condition', sa.Enum('cleared', 'snowy', 'closed_snow', 'closed_cleared', name='access_condition', schema='guidebook'), nullable=True),
    sa.Column('lift_status', sa.Enum('open', 'closed', name='lift_status', schema='guidebook'), nullable=True),
    sa.Column('condition_rating', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_quantity', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_quality', sa.Enum('excellent', 'good', 'average', 'poor', 'awful', name='condition_rating', schema='guidebook'), nullable=True),
    sa.Column('glacier_rating', sa.Enum('easy', 'possible', 'difficult', 'impossible', name='glacier_rating', schema='guidebook'), nullable=True),
    sa.Column('avalanche_signs', utils.ArrayOfEnum(Enum('no', 'danger_sign', 'recent_avalanche', 'natural_avalanche', 'accidental_avalanche', name='avalanche_signs', schema='guidebook')), nullable=True),
    sa.Column('hut_status', sa.Enum('open_guarded', 'open_non_guarded', 'closed_hut', name='hut_status', schema='guidebook'), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('outings_locales',
    sa.Column('participants', sa.String(), nullable=True),
    sa.Column('access_comment', sa.String(), nullable=True),
    sa.Column('weather', sa.String(), nullable=True),
    sa.Column('timing', sa.String(), nullable=True),
    sa.Column('conditions_levels', sa.String(), nullable=True),
    sa.Column('conditions', sa.String(), nullable=True),
    sa.Column('avalanches', sa.String(), nullable=True),
    sa.Column('hut_comment', sa.String(), nullable=True),
    sa.Column('route_description', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('outings_locales_archives',
    sa.Column('participants', sa.String(), nullable=True),
    sa.Column('access_comment', sa.String(), nullable=True),
    sa.Column('weather', sa.String(), nullable=True),
    sa.Column('timing', sa.String(), nullable=True),
    sa.Column('conditions_levels', sa.String(), nullable=True),
    sa.Column('conditions', sa.String(), nullable=True),
    sa.Column('avalanches', sa.String(), nullable=True),
    sa.Column('hut_comment', sa.String(), nullable=True),
    sa.Column('route_description', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('routes_archives',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_max', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_up', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_down', sa.SmallInteger(), nullable=True),
    sa.Column('route_length', sa.Integer(), nullable=True),
    sa.Column('difficulties_height', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_access', sa.SmallInteger(), nullable=True),
    sa.Column('height_diff_difficulties', sa.SmallInteger(), nullable=True),
    sa.Column('route_types', utils.ArrayOfEnum(Enum('return_same_way', 'loop', 'loop_hut', 'traverse', 'raid', 'expedition', name='route_type', schema='guidebook')), nullable=True),
    sa.Column('orientations', utils.ArrayOfEnum(Enum('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', name='orientation_type', schema='guidebook')), nullable=True),
    sa.Column('durations', utils.ArrayOfEnum(Enum('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '10+', name='route_duration_type', schema='guidebook')), nullable=True),
    sa.Column('glacier_gear', sa.Enum('no', 'glacier_safety_gear', 'crampons_spring', 'crampons_req', 'glacier_crampons', name='glacier_gear_type', schema='guidebook'), server_default='no', nullable=False),
    sa.Column('configuration', utils.ArrayOfEnum(Enum('edge', 'pillar', 'face', 'corridor', 'goulotte', 'glacier', name='route_configuration_type', schema='guidebook')), nullable=True),
    sa.Column('lift_access', sa.Boolean(), nullable=True),
    sa.Column('ski_rating', sa.Enum('1.1', '1.2', '1.3', '2.1', '2.2', '2.3', '3.1', '3.2', '3.3', '4.1', '4.2', '4.3', '5.1', '5.2', '5.3', '5.4', '5.5', '5.6', name='ski_rating', schema='guidebook'), nullable=True),
    sa.Column('ski_exposition', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('labande_ski_rating', sa.Enum('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', name='labande_ski_rating', schema='guidebook'), nullable=True),
    sa.Column('labande_global_rating', sa.Enum('F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+', 'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED', 'ED+', 'ED4', 'ED5', 'ED6', 'ED7', name='global_rating', schema='guidebook'), nullable=True),
    sa.Column('global_rating', sa.Enum('F', 'F+', 'PD-', 'PD', 'PD+', 'AD-', 'AD', 'AD+', 'D-', 'D', 'D+', 'TD-', 'TD', 'TD+', 'ED-', 'ED', 'ED+', 'ED4', 'ED5', 'ED6', 'ED7', name='global_rating', schema='guidebook'), nullable=True),
    sa.Column('engagement_rating', sa.Enum('I', 'II', 'III', 'IV', 'V', 'VI', name='engagement_rating', schema='guidebook'), nullable=True),
    sa.Column('risk_rating', sa.Enum('X1', 'X2', 'X3', 'X4', 'X5', name='risk_rating', schema='guidebook'), nullable=True),
    sa.Column('equipment_rating', sa.Enum('P1', 'P1+', 'P2', 'P2+', 'P3', 'P3+', 'P4', 'P4+', name='equipment_rating', schema='guidebook'), nullable=True),
    sa.Column('ice_rating', sa.Enum('1', '2', '3', '3+', '4', '4+', '5', '5+', '6', '6+', '7', '7+', name='ice_rating', schema='guidebook'), nullable=True),
    sa.Column('mixed_rating', sa.Enum('M1', 'M2', 'M3', 'M3+', 'M4', 'M4+', 'M5', 'M5+', 'M6', 'M6+', 'M7', 'M7+', 'M8', 'M8+', 'M9', 'M9+', 'M10', 'M10+', 'M11', 'M11+', 'M12', 'M12+', name='mixed_rating', schema='guidebook'), nullable=True),
    sa.Column('exposition_rock_rating', sa.Enum('E1', 'E2', 'E3', 'E4', 'E5', 'E6', name='exposition_rock_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_free_rating', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_required_rating', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('aid_rating', sa.Enum('A0', 'A0+', 'A1', 'A1+', 'A2', 'A2+', 'A3', 'A3+', 'A4', 'A4+', 'A5', 'A5+', name='aid_rating', schema='guidebook'), nullable=True),
    sa.Column('via_ferrata_rating', sa.Enum('K1', 'K2', 'K3', 'K4', 'K5', 'K6', name='via_ferrata_rating', schema='guidebook'), nullable=True),
    sa.Column('hiking_rating', sa.Enum('T1', 'T2', 'T3', 'T4', 'T5', name='hiking_rating', schema='guidebook'), nullable=True),
    sa.Column('hiking_mtb_exposition', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('snowshoe_rating', sa.Enum('R1', 'R2', 'R3', 'R4', 'R5', name='snowshoe_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_up_rating', sa.Enum('M1', 'M2', 'M3', 'M4', 'M5', name='mtb_up_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_down_rating', sa.Enum('V1', 'V2', 'V3', 'V4', 'V5', name='mtb_down_rating', schema='guidebook'), nullable=True),
    sa.Column('mtb_length_asphalt', sa.Integer(), nullable=True),
    sa.Column('mtb_length_trail', sa.Integer(), nullable=True),
    sa.Column('mtb_height_diff_portages', sa.Integer(), nullable=True),
    sa.Column('rock_types', utils.ArrayOfEnum(Enum('basalte', 'calcaire', 'conglomerat', 'craie', 'gneiss', 'gres', 'granit', 'migmatite', 'mollasse_calcaire', 'pouding', 'quartzite', 'rhyolite', 'schiste', 'trachyte', 'artificial', name='rock_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_outdoor_type', sa.Enum('single', 'multi', 'bloc', 'psicobloc', name='climbing_outdoor_type', schema='guidebook'), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('main_waypoint_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.ForeignKeyConstraint(['main_waypoint_id'], ['guidebook.documents.document_id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('routes_locales',
    sa.Column('slope', sa.String(), nullable=True),
    sa.Column('remarks', sa.String(), nullable=True),
    sa.Column('gear', sa.String(), nullable=True),
    sa.Column('external_resources', sa.String(), nullable=True),
    sa.Column('route_history', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_prefix', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('routes_locales_archives',
    sa.Column('slope', sa.String(), nullable=True),
    sa.Column('remarks', sa.String(), nullable=True),
    sa.Column('gear', sa.String(), nullable=True),
    sa.Column('external_resources', sa.String(), nullable=True),
    sa.Column('route_history', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('user_profiles_archives',
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=True),
    sa.Column('categories', utils.ArrayOfEnum(Enum('amateur', 'mountain_guide', 'mountain_leader', 'ski_instructor', 'climbing_instructor', 'mountainbike_instructor', 'paragliding_instructor', 'hut_warden', 'ski_patroller', 'avalanche_forecaster', 'club', 'institution', name='user_category', schema='guidebook')), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('waypoints_archives',
    sa.Column('waypoint_type', sa.Enum('summit', 'pass', 'lake', 'waterfall', 'locality', 'bisse', 'canyon', 'access', 'climbing_outdoor', 'climbing_indoor', 'hut', 'gite', 'shelter', 'bivouac', 'camp_site', 'base_camp', 'local_product', 'paragliding_takeoff', 'paragliding_landing', 'cave', 'waterpoint', 'weather_station', 'webcam', 'virtual', 'misc', name='waypoint_type', schema='guidebook'), nullable=False),
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('elevation_min', sa.SmallInteger(), nullable=True),
    sa.Column('prominence', sa.SmallInteger(), nullable=True),
    sa.Column('height_max', sa.SmallInteger(), nullable=True),
    sa.Column('height_median', sa.SmallInteger(), nullable=True),
    sa.Column('height_min', sa.SmallInteger(), nullable=True),
    sa.Column('routes_quantity', sa.SmallInteger(), nullable=True),
    sa.Column('climbing_outdoor_types', utils.ArrayOfEnum(Enum('single', 'multi', 'bloc', 'psicobloc', name='climbing_outdoor_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_indoor_types', utils.ArrayOfEnum(Enum('pitch', 'bloc', name='climbing_indoor_type', schema='guidebook')), nullable=True),
    sa.Column('climbing_rating_max', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('climbing_rating_min', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('climbing_rating_median', sa.Enum('2', '3a', '3b', '3c', '4a', '4b', '4c', '5a', '5a+', '5b', '5b+', '5c', '5c+', '6a', '6a+', '6b', '6b+', '6c', '6c+', '7a', '7a+', '7b', '7b+', '7c', '7c+', '8a', '8a+', '8b', '8b+', '8c', '8c+', '9a', '9a+', '9b', '9b+', '9c', '9c+', name='climbing_rating', schema='guidebook'), nullable=True),
    sa.Column('equipment_ratings', utils.ArrayOfEnum(Enum('P1', 'P1+', 'P2', 'P2+', 'P3', 'P3+', 'P4', 'P4+', name='equipment_rating', schema='guidebook')), nullable=True),
    sa.Column('climbing_styles', utils.ArrayOfEnum(Enum('slab', 'vertical', 'overhang', 'roof', 'small_pillar', 'crack_dihedral', name='climbing_style', schema='guidebook')), nullable=True),
    sa.Column('children_proof', sa.Enum('very_safe', 'safe', 'dangerous', 'very_dangerous', name='children_proof_type', schema='guidebook'), nullable=True),
    sa.Column('rain_proof', sa.Enum('exposed', 'partly_protected', 'protected', 'inside', name='rain_proof_type', schema='guidebook'), nullable=True),
    sa.Column('orientations', utils.ArrayOfEnum(Enum('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', name='orientation_type', schema='guidebook')), nullable=True),
    sa.Column('best_periods', utils.ArrayOfEnum(Enum('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec', name='month_type', schema='guidebook')), nullable=True),
    sa.Column('product_types', utils.ArrayOfEnum(Enum('farm_sale', 'restaurant', 'grocery', 'bar', 'sport_shop', name='product_type', schema='guidebook')), nullable=True),
    sa.Column('length', sa.SmallInteger(), nullable=True),
    sa.Column('slope', sa.SmallInteger(), nullable=True),
    sa.Column('ground_types', utils.ArrayOfEnum(Enum('prairie', 'scree', 'snow', name='ground_type', schema='guidebook')), nullable=True),
    sa.Column('paragliding_rating', sa.Enum('1', '2', '3', '4', '5', name='paragliding_rating', schema='guidebook'), nullable=True),
    sa.Column('exposition_rating', sa.Enum('E1', 'E2', 'E3', 'E4', name='exposition_rating', schema='guidebook'), nullable=True),
    sa.Column('rock_types', utils.ArrayOfEnum(Enum('basalte', 'calcaire', 'conglomerat', 'craie', 'gneiss', 'gres', 'granit', 'migmatite', 'mollasse_calcaire', 'pouding', 'quartzite', 'rhyolite', 'schiste', 'trachyte', 'artificial', name='rock_type', schema='guidebook')), nullable=True),
    sa.Column('weather_station_types', utils.ArrayOfEnum(Enum('temperature', 'wind_speed', 'wind_direction', 'humidity', 'pressure', 'precipitation', 'precipitation_heater', 'snow_height', 'insolation', name='weather_station_type', schema='guidebook')), nullable=True),
    sa.Column('url', sa.String(length=255), nullable=True),
    sa.Column('maps_info', sa.String(length=300), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('public_transportation_types', utils.ArrayOfEnum(Enum('train', 'bus', 'service_on_demand', 'boat', 'cable_car', name='public_transportation_type', schema='guidebook')), nullable=True),
    sa.Column('public_transportation_rating', sa.Enum('good service', 'seasonal service', 'poor service', 'nearby service', 'no service', name='public_transportation_rating', schema='guidebook'), nullable=True),
    sa.Column('snow_clearance_rating', sa.Enum('often', 'sometimes', 'progressive', 'naturally', 'closed_in_winter', 'non_applicable', name='snow_clearance_rating', schema='guidebook'), nullable=True),
    sa.Column('lift_access', sa.Boolean(), nullable=True),
    sa.Column('parking_fee', sa.Enum('yes', 'seasonal', 'no', name='parking_fee_type', schema='guidebook'), nullable=True),
    sa.Column('phone_custodian', sa.String(length=50), nullable=True),
    sa.Column('custodianship', sa.Enum('accessible_when_wardened', 'always_accessible', 'key_needed', 'no_warden', name='custodianship_type', schema='guidebook'), nullable=True),
    sa.Column('matress_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('blanket_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('gas_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('heating_unstaffed', sa.Boolean(), nullable=True),
    sa.Column('access_time', sa.Enum('1min', '5min', '10min', '15min', '20min', '30min', '45min', '1h', '1h30', '2h', '2h30', '3h', '3h+', name='access_time_type', schema='guidebook'), nullable=True),
    sa.Column('capacity', sa.SmallInteger(), nullable=True),
    sa.Column('capacity_staffed', sa.SmallInteger(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('waypoints_locales',
    sa.Column('access', sa.String(), nullable=True),
    sa.Column('access_period', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('waypoints_locales_archives',
    sa.Column('access', sa.String(), nullable=True),
    sa.Column('access_period', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('xreports_archives',
    sa.Column('elevation', sa.SmallInteger(), nullable=True),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('event_type', utils.ArrayOfEnum(Enum('avalanche', 'stone_fall', 'falling_ice', 'person_fall', 'crevasse_fall', 'roped_fall', 'physical_failure', 'lightning', 'other', name='event_type', schema='guidebook')), nullable=True),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), nullable=False),
    sa.Column('nb_participants', sa.SmallInteger(), nullable=True),
    sa.Column('nb_impacted', sa.SmallInteger(), nullable=True),
    sa.Column('rescue', sa.Boolean(), nullable=True),
    sa.Column('avalanche_level', sa.Enum('level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'level_na', name='avalanche_level', schema='guidebook'), nullable=True),
    sa.Column('avalanche_slope', sa.Enum('slope_lt_30', 'slope_30_32', 'slope_33_35', 'slope_36_38', 'slope_39_41', 'slope_42_44', 'slope_45_47', 'slope_gt_47', name='avalanche_slope', schema='guidebook'), nullable=True),
    sa.Column('severity', sa.Enum('severity_no', '1d_to_3d', '4d_to_1m', '1m_to_3m', 'more_than_3m', name='severity', schema='guidebook'), nullable=True),
    sa.Column('author_status', sa.Enum('primary_impacted', 'secondary_impacted', 'internal_witness', 'external_witness', name='author_status', schema='guidebook'), nullable=True),
    sa.Column('activity_rate', sa.Enum('activity_rate_150', 'activity_rate_50', 'activity_rate_30', 'activity_rate_20', 'activity_rate_10', 'activity_rate_5', 'activity_rate_1', name='activity_rate', schema='guidebook'), nullable=True),
    sa.Column('nb_outings', sa.Enum('nb_outings_4', 'nb_outings_9', 'nb_outings_14', 'nb_outings_15', name='nb_outings', schema='guidebook'), nullable=True),
    sa.Column('age', sa.SmallInteger(), nullable=True),
    sa.Column('gender', sa.Enum('male', 'female', name='gender', schema='guidebook'), nullable=True),
    sa.Column('previous_injuries', sa.Enum('no', 'previous_injuries_2', 'previous_injuries_3', name='previous_injuries', schema='guidebook'), nullable=True),
    sa.Column('autonomy', sa.Enum('non_autonomous', 'autonomous', 'initiator', 'expert', name='autonomy', schema='guidebook'), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('xreports_locales',
    sa.Column('place', sa.String(), nullable=True),
    sa.Column('route_study', sa.String(), nullable=True),
    sa.Column('conditions', sa.String(), nullable=True),
    sa.Column('training', sa.String(), nullable=True),
    sa.Column('motivations', sa.String(), nullable=True),
    sa.Column('group_management', sa.String(), nullable=True),
    sa.Column('risk', sa.String(), nullable=True),
    sa.Column('time_management', sa.String(), nullable=True),
    sa.Column('safety', sa.String(), nullable=True),
    sa.Column('reduce_impact', sa.String(), nullable=True),
    sa.Column('increase_impact', sa.String(), nullable=True),
    sa.Column('modifications', sa.String(), nullable=True),
    sa.Column('other_comments', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('xreports_locales_archives',
    sa.Column('place', sa.String(), nullable=True),
    sa.Column('route_study', sa.String(), nullable=True),
    sa.Column('conditions', sa.String(), nullable=True),
    sa.Column('training', sa.String(), nullable=True),
    sa.Column('motivations', sa.String(), nullable=True),
    sa.Column('group_management', sa.String(), nullable=True),
    sa.Column('risk', sa.String(), nullable=True),
    sa.Column('time_management', sa.String(), nullable=True),
    sa.Column('safety', sa.String(), nullable=True),
    sa.Column('reduce_impact', sa.String(), nullable=True),
    sa.Column('increase_impact', sa.String(), nullable=True),
    sa.Column('modifications', sa.String(), nullable=True),
    sa.Column('other_comments', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.documents_locales_archives.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=200), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('forum_username', sa.String(length=25), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('email_validated', sa.Boolean(), nullable=False),
    sa.Column('email_to_validate', sa.String(length=200), nullable=True),
    sa.Column('moderator', sa.Boolean(), nullable=False),
    sa.Column('validation_nonce', sa.String(length=200), nullable=True),
    sa.Column('validation_nonce_expire', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password', sa.String(length=255), nullable=False),
    sa.Column('last_modified', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.Column('is_profile_public', sa.Boolean(), server_default='FALSE', nullable=False),
    sa.Column('feed_filter_activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), server_default='{}', nullable=False),
    sa.Column('feed_followed_only', sa.Boolean(), server_default='FALSE', nullable=False),
    sa.ForeignKeyConstraint(['id'], ['guidebook.user_profiles.document_id'], ),
    sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('forum_username'),
    sa.UniqueConstraint('username'),
    sa.UniqueConstraint('validation_nonce'),
    schema='users'
    )
    op.create_index(op.f('ix_users_user_email_validated'), 'user', ['email_validated'], unique=False, schema='users')
    op.create_index(op.f('ix_users_user_last_modified'), 'user', ['last_modified'], unique=False, schema='users')
    op.create_table('association_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parent_document_id', sa.Integer(), nullable=False),
    sa.Column('parent_document_type', sa.String(length=1), nullable=False),
    sa.Column('child_document_id', sa.Integer(), nullable=False),
    sa.Column('child_document_type', sa.String(length=1), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('is_creation', sa.Boolean(), nullable=False),
    sa.Column('written_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['child_document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['parent_document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_association_log_written_at'), 'association_log', ['written_at'], unique=False, schema='guidebook')
    op.create_table('feed_document_changes',
    sa.Column('change_id', sa.Integer(), nullable=False),
    sa.Column('time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('change_type', sa.Enum('created', 'updated', 'added_photos', name='feed_change_type', schema='guidebook'), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('document_type', sa.String(length=1), nullable=False),
    sa.Column('activities', utils.ArrayOfEnum(Enum('skitouring', 'snow_ice_mixed', 'mountain_climbing', 'rock_climbing', 'ice_climbing', 'hiking', 'snowshoeing', 'paragliding', 'mountain_biking', 'via_ferrata', name='activity_type', schema='guidebook')), server_default='{}', nullable=False),
    sa.Column('area_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
    sa.Column('user_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
    sa.Column('image1_id', sa.Integer(), nullable=True),
    sa.Column('image2_id', sa.Integer(), nullable=True),
    sa.Column('image3_id', sa.Integer(), nullable=True),
    sa.Column('more_images', sa.Boolean(), server_default='FALSE', nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['image1_id'], ['guidebook.images.document_id'], ),
    sa.ForeignKeyConstraint(['image2_id'], ['guidebook.images.document_id'], ),
    sa.ForeignKeyConstraint(['image3_id'], ['guidebook.images.document_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('change_id'),
    schema='guidebook'
    )
    op.create_index('ix_guidebook_feed_document_changes_time_and_change_id', 'feed_document_changes', [sa.text('time DESC'), 'change_id'], unique=False, schema='guidebook', postgresql_using='btree')
    op.create_table('feed_filter_area',
    sa.Column('area_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['guidebook.areas.document_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('area_id', 'user_id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_feed_filter_area_user_id'), 'feed_filter_area', ['user_id'], unique=False, schema='guidebook')
    op.create_table('feed_followed_users',
    sa.Column('followed_user_id', sa.Integer(), nullable=False),
    sa.Column('follower_user_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('followed_user_id != follower_user_id', name='check_feed_followed_user_self_follow'),
    sa.ForeignKeyConstraint(['followed_user_id'], ['users.user.id'], ),
    sa.ForeignKeyConstraint(['follower_user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('followed_user_id', 'follower_user_id'),
    schema='guidebook'
    )
    op.create_table('history_metadata',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('comment', sa.String(length=200), nullable=True),
    sa.Column('written_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_history_metadata_user_id'), 'history_metadata', ['user_id'], unique=False, schema='guidebook')
    op.create_index(op.f('ix_guidebook_history_metadata_written_at'), 'history_metadata', ['written_at'], unique=False, schema='guidebook')
    op.create_table('subscriber_table',
    sa.Column('list_subscriber', sa.String(length=50), nullable=False),
    sa.Column('user_subscriber', sa.String(length=200), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date_subscriber', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('update_subscriber', sa.DateTime(), nullable=True),
    sa.Column('visibility_subscriber', sa.String(length=20), nullable=True),
    sa.Column('reception_subscriber', sa.String(length=20), nullable=True),
    sa.Column('bounce_subscriber', sa.String(length=35), nullable=True),
    sa.Column('bounce_score_subscriber', sa.Integer(), nullable=True),
    sa.Column('comment_subscriber', sa.String(length=150), nullable=True),
    sa.Column('subscribed_subscriber', sa.Integer(), nullable=True),
    sa.Column('included_subscriber', sa.Integer(), nullable=True),
    sa.Column('include_sources_subscriber', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('list_subscriber', 'user_subscriber'),
    schema='sympa'
    )
    op.create_table('token',
    sa.Column('value', sa.String(), nullable=False),
    sa.Column('expire', sa.DateTime(timezone=True), nullable=False),
    sa.Column('userid', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['userid'], ['users.user.id'], ),
    sa.PrimaryKeyConstraint('value'),
    schema='users'
    )
    op.create_index(op.f('ix_users_token_expire'), 'token', ['expire'], unique=False, schema='users')
    op.create_table('documents_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.Column('document_archive_id', sa.Integer(), nullable=False),
    sa.Column('document_locales_archive_id', sa.Integer(), nullable=False),
    sa.Column('document_geometry_archive_id', sa.Integer(), nullable=True),
    sa.Column('history_metadata_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_archive_id'], ['guidebook.documents_archives.id'], ),
    sa.ForeignKeyConstraint(['document_geometry_archive_id'], ['guidebook.documents_geometries_archives.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
    sa.ForeignKeyConstraint(['document_locales_archive_id'], ['guidebook.documents_locales_archives.id'], ),
    sa.ForeignKeyConstraint(['history_metadata_id'], ['guidebook.history_metadata.id'], ),
    sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='guidebook'
    )
    op.create_index(op.f('ix_guidebook_documents_versions_document_id'), 'documents_versions', ['document_id'], unique=False, schema='guidebook')
    op.create_index(op.f('ix_guidebook_documents_versions_history_metadata_id'), 'documents_versions', ['history_metadata_id'], unique=False, schema='guidebook')
    # ### end Alembic commands ###

    # remove dimension constraint for `geom_detail` so that geometries with 2, 3 or 4 dimensions can
    # be stored in the same column
    op.drop_constraint('enforce_dims_geom_detail', 'documents_geometries', schema='guidebook')
    op.drop_constraint('enforce_dims_geom_detail', 'documents_geometries_archives', schema='guidebook')

    # functions and triggers
    op.create_function(function_update_cache_version_time)
    op.execute("""
CREATE TRIGGER guidebook_cache_versions_update
BEFORE UPDATE ON guidebook.cache_versions
FOR EACH ROW
EXECUTE PROCEDURE guidebook.update_cache_version_time();
""")

    op.create_function(function_create_cache_version)
    op.execute("""
CREATE TRIGGER guidebook_documents_insert
AFTER INSERT ON guidebook.documents
FOR EACH ROW
EXECUTE PROCEDURE guidebook.create_cache_version();
""")

    op.create_function(function_simplify_geom_detail)
    op.execute("""
CREATE TRIGGER
guidebook_documents_geometries_insert_or_update
BEFORE INSERT OR UPDATE OF geom_detail
ON guidebook.documents_geometries
FOR EACH ROW
EXECUTE PROCEDURE guidebook.simplify_geom_detail();

CREATE TRIGGER
guidebook_documents_geometries_archives_geometries_insert_or_update
BEFORE INSERT OR UPDATE OF geom_detail
ON guidebook.documents_geometries_archives
FOR EACH ROW
EXECUTE PROCEDURE guidebook.simplify_geom_detail();
""")

    op.create_function(function_check_feed_ids)
    op.execute("""
CREATE TRIGGER guidebook_feed_document_changes_insert
AFTER INSERT OR UPDATE ON guidebook.feed_document_changes
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_ids();
""")

    op.create_function(function_check_feed_user_ids)
    op.execute("""
CREATE TRIGGER users_user_delete
AFTER DELETE ON users.user
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_user_ids();
""")

    op.create_function(function_check_feed_area_ids)
    op.execute("""
CREATE TRIGGER guidebook_areas_delete
AFTER DELETE ON guidebook.areas
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_area_ids();
""")

    # Make sure that user email changes are propagated to mailing lists as well
    op.create_function(function_check_forum_username)
    op.create_check_constraint(
        'forum_username_check_constraint',
        'user',
        'users.check_forum_username(forum_username)',
        schema='users'
    )

    op.create_function(function_update_mailinglists_email)
    op.execute("""
CREATE TRIGGER users_email_update
AFTER UPDATE ON users.user
FOR EACH ROW
WHEN (OLD.email IS DISTINCT FROM NEW.email)
EXECUTE PROCEDURE users.update_mailinglists_email();
""")

    op.create_function(function_update_cache_version)
    op.create_function(function_increment_cache_version)
    op.create_function(function_increment_cache_versions)
    op.create_function(function_update_cache_version_of_linked_documents)
    op.create_function(function_get_waypoints_for_routes)
    op.create_function(function_update_cache_version_of_main_waypoint_routes)
    op.create_function(function_update_cache_version_of_route)
    op.create_function(function_update_cache_version_of_routes)
    op.create_function(function_update_cache_version_of_waypoints)
    op.create_function(function_update_cache_version_of_outing)
    op.create_function(function_update_cache_version_for_user)
    op.create_function(function_update_cache_version_for_area)
    op.create_function(function_update_cache_version_for_map)

    # views
    op.create_view(view_waypoints_for_routes)
    op.create_view(view_waypoints_for_outings)
    op.create_view(view_users_for_outings)
    op.create_view(view_routes_for_outings)


def downgrade():
    # views
    op.drop_view(view_waypoints_for_routes)
    op.drop_view(view_waypoints_for_outings)
    op.drop_view(view_users_for_outings)
    op.drop_view(view_routes_for_outings)

    # functions and triggers
    op.execute('DROP TRIGGER guidebook_cache_versions_update ON guidebook.cache_versions;')
    op.drop_function(function_update_cache_version_time)

    op.execute('DROP TRIGGER guidebook_documents_insert ON guidebook.documents;')
    op.drop_function(function_create_cache_version)

    op.execute('DROP TRIGGER guidebook_documents_geometries_insert_or_update ON guidebook.documents_geometries;')
    op.execute('DROP TRIGGER guidebook_documents_geometries_archives_geometries_insert_or_update ON guidebook.documents_geometries_archives;')
    op.drop_function(function_simplify_geom_detail)

    op.execute('DROP TRIGGER guidebook_feed_document_changes_insert ON guidebook.feed_document_changes;')
    op.drop_function(function_check_feed_ids)

    op.execute('DROP TRIGGER users_user_delete ON users.user;')
    op.drop_function(function_check_feed_user_ids)

    op.execute('DROP TRIGGER guidebook_areas_delete ON guidebook.areas;')
    op.drop_function(function_check_feed_area_ids)

    op.drop_constraint('forum_username_check_constraint', 'user', schema='users')
    op.drop_function(function_check_forum_username)

    op.execute('DROP TRIGGER users_email_update ON users.user;')
    op.drop_function(function_update_mailinglists_email)

    op.drop_function(function_update_cache_version_for_map)
    op.drop_function(function_update_cache_version_for_area)
    op.drop_function(function_update_cache_version_for_user)
    op.drop_function(function_update_cache_version_of_outing)
    op.drop_function(function_update_cache_version_of_waypoints)
    op.drop_function(function_update_cache_version_of_routes)
    op.drop_function(function_update_cache_version_of_route)
    op.drop_function(function_update_cache_version_of_main_waypoint_routes)
    op.drop_function(function_get_waypoints_for_routes)
    op.drop_function(function_update_cache_version_of_linked_documents)
    op.drop_function(function_increment_cache_versions)
    op.drop_function(function_increment_cache_version)
    op.drop_function(function_update_cache_version)

    ### commands auto generated by Alembic  ###
    op.drop_index(op.f('ix_guidebook_documents_versions_history_metadata_id'), table_name='documents_versions', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_documents_versions_document_id'), table_name='documents_versions', schema='guidebook')
    op.drop_table('documents_versions', schema='guidebook')
    op.drop_index(op.f('ix_users_token_expire'), table_name='token', schema='users')
    op.drop_table('token', schema='users')
    op.drop_table('subscriber_table', schema='sympa')
    op.drop_index(op.f('ix_guidebook_history_metadata_written_at'), table_name='history_metadata', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_history_metadata_user_id'), table_name='history_metadata', schema='guidebook')
    op.drop_table('history_metadata', schema='guidebook')
    op.drop_table('feed_followed_users', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_feed_filter_area_user_id'), table_name='feed_filter_area', schema='guidebook')
    op.drop_table('feed_filter_area', schema='guidebook')
    op.drop_index('ix_guidebook_feed_document_changes_time_and_change_id', table_name='feed_document_changes', schema='guidebook')
    op.drop_table('feed_document_changes', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_association_log_written_at'), table_name='association_log', schema='guidebook')
    op.drop_table('association_log', schema='guidebook')
    op.drop_index(op.f('ix_users_user_last_modified'), table_name='user', schema='users')
    op.drop_index(op.f('ix_users_user_email_validated'), table_name='user', schema='users')
    op.drop_table('user', schema='users')
    op.drop_table('xreports_locales_archives', schema='guidebook')
    op.drop_table('xreports_locales', schema='guidebook')
    op.drop_table('xreports_archives', schema='guidebook')
    op.drop_table('waypoints_locales_archives', schema='guidebook')
    op.drop_table('waypoints_locales', schema='guidebook')
    op.drop_table('waypoints_archives', schema='guidebook')
    op.drop_table('user_profiles_archives', schema='guidebook')
    op.drop_table('routes_locales_archives', schema='guidebook')
    op.drop_table('routes_locales', schema='guidebook')
    op.drop_table('routes_archives', schema='guidebook')
    op.drop_table('outings_locales_archives', schema='guidebook')
    op.drop_table('outings_locales', schema='guidebook')
    op.drop_table('outings_archives', schema='guidebook')
    op.drop_table('maps_archives', schema='guidebook')
    op.drop_table('map_associations', schema='guidebook')
    op.drop_table('images_archives', schema='guidebook')
    op.drop_table('documents_topics', schema='guidebook')
    op.drop_table('books_archives', schema='guidebook')
    op.drop_table('articles_archives', schema='guidebook')
    op.drop_table('areas_archives', schema='guidebook')
    op.drop_table('area_associations', schema='guidebook')
    op.drop_table('xreports', schema='guidebook')
    op.drop_table('waypoints', schema='guidebook')
    op.drop_table('user_profiles', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_routes_main_waypoint_id'), table_name='routes', schema='guidebook')
    op.drop_table('routes', schema='guidebook')
    op.drop_table('outings', schema='guidebook')
    op.drop_table('maps', schema='guidebook')
    op.drop_table('images', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_documents_locales_archives_document_id'), table_name='documents_locales_archives', schema='guidebook')
    op.drop_table('documents_locales_archives', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_documents_locales_document_id'), table_name='documents_locales', schema='guidebook')
    op.drop_table('documents_locales', schema='guidebook')
    op.drop_table('documents_geometries_archives', schema='guidebook')
    op.drop_table('documents_geometries', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_documents_archives_type'), table_name='documents_archives', schema='guidebook')
    op.drop_table('documents_archives', schema='guidebook')
    op.drop_table('cache_versions', schema='guidebook')
    op.drop_table('books', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_associations_parent_document_type'), table_name='associations', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_associations_parent_document_id'), table_name='associations', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_associations_child_document_type'), table_name='associations', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_associations_child_document_id'), table_name='associations', schema='guidebook')
    op.drop_table('associations', schema='guidebook')
    op.drop_table('articles', schema='guidebook')
    op.drop_table('areas', schema='guidebook')
    op.drop_table('langs', schema='guidebook')
    op.drop_table('es_sync_status', schema='guidebook')
    op.drop_index(op.f('ix_guidebook_documents_type'), table_name='documents', schema='guidebook')
    op.drop_table('documents', schema='guidebook')
    # ### end Alembic commands ###

    # remove all enum types
    drop_enum('access_condition', schema='guidebook')
    drop_enum('access_time_type', schema='guidebook')
    drop_enum('activity_rate', schema='guidebook')
    drop_enum('activity_type', schema='guidebook')
    drop_enum('aid_rating', schema='guidebook')
    drop_enum('area_type', schema='guidebook')
    drop_enum('article_category', schema='guidebook')
    drop_enum('article_type', schema='guidebook')
    drop_enum('author_status', schema='guidebook')
    drop_enum('autonomy', schema='guidebook')
    drop_enum('avalanche_level', schema='guidebook')
    drop_enum('avalanche_signs', schema='guidebook')
    drop_enum('avalanche_slope', schema='guidebook')
    drop_enum('book_type', schema='guidebook')
    drop_enum('children_proof_type', schema='guidebook')
    drop_enum('climbing_indoor_type', schema='guidebook')
    drop_enum('climbing_outdoor_type', schema='guidebook')
    drop_enum('climbing_rating', schema='guidebook')
    drop_enum('climbing_style', schema='guidebook')
    drop_enum('condition_rating', schema='guidebook')
    drop_enum('custodianship_type', schema='guidebook')
    drop_enum('engagement_rating', schema='guidebook')
    drop_enum('equipment_rating', schema='guidebook')
    drop_enum('event_type', schema='guidebook')
    drop_enum('exposition_rating', schema='guidebook')
    drop_enum('exposition_rock_rating', schema='guidebook')
    drop_enum('feed_change_type', schema='guidebook')
    drop_enum('frequentation_type', schema='guidebook')
    drop_enum('gender', schema='guidebook')
    drop_enum('glacier_gear_type', schema='guidebook')
    drop_enum('glacier_rating', schema='guidebook')
    drop_enum('global_rating', schema='guidebook')
    drop_enum('ground_type', schema='guidebook')
    drop_enum('hiking_rating', schema='guidebook')
    drop_enum('hut_status', schema='guidebook')
    drop_enum('ice_rating', schema='guidebook')
    drop_enum('image_category', schema='guidebook')
    drop_enum('image_type', schema='guidebook')
    drop_enum('labande_ski_rating', schema='guidebook')
    drop_enum('lift_status', schema='guidebook')
    drop_enum('map_editor', schema='guidebook')
    drop_enum('map_scale', schema='guidebook')
    drop_enum('mixed_rating', schema='guidebook')
    drop_enum('month_type', schema='guidebook')
    drop_enum('mtb_down_rating', schema='guidebook')
    drop_enum('mtb_up_rating', schema='guidebook')
    drop_enum('nb_outings', schema='guidebook')
    drop_enum('orientation_type', schema='guidebook')
    drop_enum('paragliding_rating', schema='guidebook')
    drop_enum('parking_fee_type', schema='guidebook')
    drop_enum('previous_injuries', schema='guidebook')
    drop_enum('product_type', schema='guidebook')
    drop_enum('public_transportation_rating', schema='guidebook')
    drop_enum('public_transportation_type', schema='guidebook')
    drop_enum('quality_type', schema='guidebook')
    drop_enum('rain_proof_type', schema='guidebook')
    drop_enum('risk_rating', schema='guidebook')
    drop_enum('rock_type', schema='guidebook')
    drop_enum('route_configuration_type', schema='guidebook')
    drop_enum('route_duration_type', schema='guidebook')
    drop_enum('route_type', schema='guidebook')
    drop_enum('severity', schema='guidebook')
    drop_enum('ski_rating', schema='guidebook')
    drop_enum('snow_clearance_rating', schema='guidebook')
    drop_enum('snowshoe_rating', schema='guidebook')
    drop_enum('user_category', schema='guidebook')
    drop_enum('via_ferrata_rating', schema='guidebook')
    drop_enum('waypoint_type', schema='guidebook')
    drop_enum('weather_station_type', schema='guidebook')
