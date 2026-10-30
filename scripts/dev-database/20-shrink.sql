-- Keeps only what 10-select.sql selected. The foreign keys are not created yet at this point
-- (they are restored in a last step, on the small database, and that doubles as an integrity check).

set work_mem = '256MB';

-- Tables with one row per kept document
do $$
declare
  t text;
begin
  foreach t in array array[
    'documents', 'areas', 'articles', 'books', 'coverages', 'images', 'maps', 'outings', 'routes',
    'user_profiles', 'waypoints', 'xreports', 'documents_locales', 'documents_geometries',
    'cache_versions', 'area_associations'
  ] loop
    perform devdb.shrink(('guidebook.' || t)::regclass, 'document_id in (select document_id from devdb.keep_doc)');
  end loop;
end
$$;

-- Versions, and the archives they point to
select devdb.shrink('guidebook.documents_versions', 'id in (select id from devdb.keep_version)');
select devdb.shrink('guidebook.documents_archives', 'id in (select document_archive_id from guidebook.documents_versions)');
select devdb.shrink('guidebook.documents_locales_archives', 'id in (select document_locales_archive_id from guidebook.documents_versions)');
select devdb.shrink('guidebook.documents_geometries_archives', 'id in (select document_geometry_archive_id from guidebook.documents_versions)');
select devdb.shrink('guidebook.history_metadata', 'id in (select history_metadata_id from guidebook.documents_versions)');

do $$
declare
  t text;
begin
  foreach t in array array[
    'areas', 'articles', 'books', 'images', 'maps', 'outings', 'routes', 'user_profiles', 'waypoints', 'xreports'
  ] loop
    perform devdb.shrink(('guidebook.' || t || '_archives')::regclass, 'id in (select id from guidebook.documents_archives)');
  end loop;

  foreach t in array array['outings', 'routes', 'waypoints', 'xreports'] loop
    perform devdb.shrink(('guidebook.' || t || '_locales')::regclass, 'id in (select id from guidebook.documents_locales)');
    perform devdb.shrink(('guidebook.' || t || '_locales_archives')::regclass, 'id in (select id from guidebook.documents_locales_archives)');
  end loop;
end
$$;

-- Associations: both ends must be kept
select devdb.shrink('guidebook.associations',
  'parent_document_id in (select document_id from devdb.keep_doc) and child_document_id in (select document_id from devdb.keep_doc)');
select devdb.shrink('guidebook.association_log',
  'parent_document_id in (select document_id from devdb.keep_doc) and child_document_id in (select document_id from devdb.keep_doc)');
select devdb.shrink('guidebook.map_associations',
  'document_id in (select document_id from devdb.keep_doc) and topo_map_id in (select document_id from devdb.keep_doc)');

-- Public transport (Navitia): the stop areas of the kept waypoints. Nothing is requested from Navitia.
select devdb.shrink('guidebook.waypoints_stopareas', 'waypoint_id in (select document_id from devdb.keep_doc)');
select devdb.shrink('guidebook.stopareas', 'stoparea_id in (select stoparea_id from guidebook.waypoints_stopareas)');

-- Home page feed
select devdb.shrink('guidebook.feed_document_changes',
  'document_id in (select document_id from devdb.keep_doc) and user_id in (select user_id from devdb.keep_user)');

-- Users, only those which are related to kept data
select devdb.shrink('users.user', 'id in (select user_id from devdb.keep_user)');

-- What private accounts did (history, associations) is attributed to a single former member
insert into users.user (id, username, name, forum_username, email, email_validated, moderator, password,
                        last_modified, lang, is_profile_public, blocked, robot, ratelimit_times)
values (-1, 'former-member', 'Former member', 'former-member', 'former-member@example.com', false, false,
        '$2b$12$JPOxvA1AUc4LRUE6OJMlLeFoKoTYjfGpnBsC4tSE7VhAh3e/AmeGi', now(), 'en', false, true, false, 0);
-- (like every user, it needs a profile document)
insert into guidebook.documents (document_id, version, type, protected, quality) values (-1, 1, 'u', false, 'empty');
insert into guidebook.user_profiles (document_id) values (-1);
update guidebook.history_metadata set user_id = -1 where user_id not in (select id from users.user);
update guidebook.association_log set user_id = -1 where user_id not in (select id from users.user);

-- Forum topics do not exist in a dev environment
truncate guidebook.documents_topics;

-- References to rows that are not kept anymore. They are only in old versions, or in lists of ids.
update guidebook.routes_archives set main_waypoint_id = null
  where main_waypoint_id is not null
    and main_waypoint_id not in (select document_id from guidebook.documents);
update guidebook.documents_archives set redirects_to = null
  where redirects_to is not null
    and redirects_to not in (select document_id from guidebook.documents);
update guidebook.feed_document_changes set image1_id = null where image1_id not in (select document_id from guidebook.images);
update guidebook.feed_document_changes set image2_id = null where image2_id not in (select document_id from guidebook.images);
update guidebook.feed_document_changes set image3_id = null where image3_id not in (select document_id from guidebook.images);
update guidebook.feed_document_changes set user_ids = coalesce((select array_agg(u) from unnest(user_ids) u where u in (select id from users.user)), '{}');

-- Lighter geometries. The srid is 3857, the tolerance is in meters: the borders of the areas
-- (huge polygons) and GPS tracks do not need to be accurate in a dev database.
update guidebook.documents_geometries g
  set geom_detail = st_simplifypreservetopology(g.geom_detail, 100)
  from guidebook.areas a
  where a.document_id = g.document_id and g.geom_detail is not null;
update guidebook.documents_geometries g
  set geom_detail = st_simplifypreservetopology(g.geom_detail, 10)
  from guidebook.documents d
  where d.document_id = g.document_id and d.type in ('o', 'r') and g.geom_detail is not null;
