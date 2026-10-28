-- Selects the documents (devdb.keep_doc), the versions (devdb.keep_version) and the users
-- (devdb.keep_user) that are kept. Nothing is modified in the guidebook tables here.
--
-- The first reason given to a document is the one that is stored (the order of the steps matters).

set work_mem = '256MB';

do $$
begin
  if (select count(*) from devdb.zone z join guidebook.areas a on a.document_id = z.area_id)
     <> (select count(*) from devdb.zone) then
    raise exception 'devdb.zone contains an id that is not an area';
  end if;
end
$$;

-- 1. Always kept: small document types, referenced from everywhere. All the xreports are kept
-- as well (a few hundred, and precious edge cases: their free text is replaced by anonymization).
insert into devdb.keep_doc
  select document_id, 'always:' || type from guidebook.documents
  where type in ('a', 'b', 'c', 'm', 'v', 'x')
  on conflict do nothing;

-- 2. Edge cases, outside of the zones too. Each rule keeps `edge_per_rule` documents, picked in a
-- deterministic but arbitrary way (document_id % 1009 mixes the ids) so that the result is stable.
-- Edge cases keep their whole history (see below).

-- 2.1 every quality level of each type
insert into devdb.keep_doc
  select document_id, 'edge:quality'
  from (select d.document_id,
               row_number() over (partition by d.type, d.quality order by d.document_id % 1009, d.document_id) rn
        from guidebook.documents d where d.type in ('w', 'r', 'o', 'c', 'b')) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.2 protected documents (only moderators can edit them)
insert into devdb.keep_doc
  select document_id, 'edge:protected'
  from (select d.document_id,
               row_number() over (partition by d.type order by d.document_id % 1009, d.document_id) rn
        from guidebook.documents d where d.protected and d.type in ('w', 'r', 'o', 'c', 'i', 'a', 'b')) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.3 documents merged into another one (redirects_to, the target is added by the closure)
insert into devdb.keep_doc
  select document_id, 'edge:redirect'
  from (select d.document_id,
               row_number() over (partition by d.type order by d.document_id % 1009, d.document_id) rn
        from guidebook.documents d where d.redirects_to is not null and d.type in ('w', 'r', 'o', 'c', 'i')) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.4 the longest descriptions
insert into devdb.keep_doc
  select document_id, 'edge:long-description'
  from (select l.document_id,
               row_number() over (partition by d.type order by max(length(coalesce(l.description, ''))) desc, l.document_id) rn
        from guidebook.documents_locales l join guidebook.documents d using (document_id)
        where d.type in ('w', 'r', 'o', 'c')
        group by l.document_id, d.type) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.5 documents available in many langs
insert into devdb.keep_doc
  select document_id, 'edge:many-langs'
  from (select l.document_id,
               row_number() over (partition by d.type order by count(distinct l.lang) desc, l.document_id) rn
        from guidebook.documents_locales l join guidebook.documents d using (document_id)
        where d.type in ('w', 'r', 'o', 'c')
        group by l.document_id, d.type) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.6 each lang other than French
insert into devdb.keep_doc
  select document_id, 'edge:lang'
  from (select l.document_id,
               row_number() over (partition by l.lang order by l.document_id % 1009, l.document_id) rn
        from guidebook.documents_locales l join guidebook.documents d using (document_id)
        where d.type in ('w', 'r', 'o', 'c') and l.lang <> 'fr') s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.7 waypoints and routes without any geometry, or without a point
insert into devdb.keep_doc
  select document_id, 'edge:no-geometry'
  from (select d.document_id,
               row_number() over (partition by d.type order by d.document_id % 1009, d.document_id) rn
        from guidebook.documents d left join guidebook.documents_geometries g using (document_id)
        where d.type in ('w', 'r') and (g.document_id is null or g.geom is null)) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.8 the most associated waypoints and routes
insert into devdb.keep_doc
  select document_id, 'edge:many-associations'
  from (select c.document_id,
               row_number() over (partition by d.type order by c.n desc, c.document_id) rn
        from (select document_id, count(*) n
              from (select parent_document_id document_id from guidebook.associations
                    union all select child_document_id from guidebook.associations) x
              group by document_id) c
        join guidebook.documents d using (document_id)
        where d.type in ('w', 'r')) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.9 titles with characters that are not latin, or which are special in HTML / URLs
insert into devdb.keep_doc
  select document_id, 'edge:title'
  from (select l.document_id,
               row_number() over (order by l.document_id % 1009, l.document_id) rn
        from guidebook.documents_locales l join guidebook.documents d using (document_id)
        where d.type in ('w', 'r', 'o', 'c') and l.title ~ '[^\u0001-ɏ]') s
  where rn <= 2 * devdb.p('edge_per_rule')::int
  on conflict do nothing;
insert into devdb.keep_doc
  select document_id, 'edge:title'
  from (select l.document_id,
               row_number() over (order by l.document_id % 1009, l.document_id) rn
        from guidebook.documents_locales l join guidebook.documents d using (document_id)
        where d.type in ('w', 'r', 'o', 'c') and l.title ~ '[<>&"%\\]') s
  where rn <= 2 * devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.10 waypoints with the most stopareas (also when they are outside of the zones)
insert into devdb.keep_doc
  select waypoint_id, 'edge:many-stopareas'
  from (select waypoint_id, row_number() over (order by count(*) desc, waypoint_id) rn
        from guidebook.waypoints_stopareas group by waypoint_id) s
  where rn <= 2 * devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 2.11 outings with the most images
insert into devdb.keep_doc
  select parent_document_id, 'edge:many-images'
  from (select parent_document_id, row_number() over (order by count(*) desc, parent_document_id) rn
        from guidebook.associations
        where parent_document_type = 'o' and child_document_type = 'i'
        group by parent_document_id) s
  where rn <= devdb.p('edge_per_rule')::int
  on conflict do nothing;

-- 3. Zones: all the waypoints and routes, and the recent outings (plus a sample of older ones)
create table devdb.zone_doc as
  select distinct aa.document_id
  from guidebook.area_associations aa join devdb.zone z using (area_id);

insert into devdb.keep_doc
  select d.document_id, 'zone:' || d.type
  from guidebook.documents d join devdb.zone_doc z using (document_id)
  where d.type in ('w', 'r')
  on conflict do nothing;

insert into devdb.keep_doc
  select o.document_id, 'zone:o'
  from guidebook.outings o join devdb.zone_doc z using (document_id)
  where o.date_start >= devdb.p('outing_since')::date
     or (o.document_id % 100) < devdb.p('outing_sample_pct')::int
  on conflict do nothing;

-- 4. Closure: what the kept documents need to be consistent (a route needs its main waypoint,
-- the routes of its outings need their waypoints, etc.), until nothing is added anymore.
create function devdb.close_over_documents() returns void language plpgsql as $$
declare
  added integer;
  total integer;
begin
  loop
    total := 0;

    -- routes of the kept outings
    insert into devdb.keep_doc
      select distinct a.parent_document_id, 'closure:route-of-outing'
      from guidebook.associations a join devdb.keep_doc k on k.document_id = a.child_document_id
      where a.parent_document_type = 'r' and a.child_document_type = 'o'
      on conflict do nothing;
    get diagnostics added = row_count; total := total + added;

    -- waypoints of the kept routes
    insert into devdb.keep_doc
      select distinct a.parent_document_id, 'closure:waypoint-of-route'
      from guidebook.associations a join devdb.keep_doc k on k.document_id = a.child_document_id
      where a.parent_document_type = 'w' and a.child_document_type = 'r'
      on conflict do nothing;
    get diagnostics added = row_count; total := total + added;

    -- main waypoints of the kept routes (foreign key)
    insert into devdb.keep_doc
      select distinct r.main_waypoint_id, 'closure:main-waypoint'
      from guidebook.routes r join devdb.keep_doc k on k.document_id = r.document_id
      where r.main_waypoint_id is not null
      on conflict do nothing;
    get diagnostics added = row_count; total := total + added;

    -- parent waypoints of the kept waypoints
    insert into devdb.keep_doc
      select distinct a.parent_document_id, 'closure:parent-waypoint'
      from guidebook.associations a join devdb.keep_doc k on k.document_id = a.child_document_id
      where a.parent_document_type = 'w' and a.child_document_type = 'w'
      on conflict do nothing;
    get diagnostics added = row_count; total := total + added;

    -- targets of redirections (foreign key)
    insert into devdb.keep_doc
      select distinct d.redirects_to, 'closure:redirect-target'
      from guidebook.documents d join devdb.keep_doc k on k.document_id = d.document_id
      where d.redirects_to is not null
      on conflict do nothing;
    get diagnostics added = row_count; total := total + added;

    exit when total = 0;
  end loop;
end
$$;
select devdb.close_over_documents();

-- 5. Images attached to the kept documents (at most `images_per_document` per document, the most
-- recent ones), and the profiles of the people who took part in the kept outings, xreports, articles.
insert into devdb.keep_doc
  select image_id, 'image'
  from (select a.child_document_id image_id,
               row_number() over (partition by a.parent_document_id order by a.child_document_id desc) rn
        from guidebook.associations a join devdb.keep_doc k on k.document_id = a.parent_document_id
        where a.child_document_type = 'i' and a.parent_document_type in ('w', 'r', 'o', 'x', 'c', 'b', 'a')) s
  where rn <= devdb.p('images_per_document')::int
  on conflict do nothing;

insert into devdb.keep_doc
  select distinct a.parent_document_id, 'profile-of-participant'
  from guidebook.associations a join devdb.keep_doc k on k.document_id = a.child_document_id
  where a.parent_document_type = 'u' and a.child_document_type in ('o', 'x', 'c')
  on conflict do nothing;

-- 6. Versions and users. Only the last version of each (document, lang) is kept, except for the
-- edge cases and for a sample of the documents, which keep their whole history. Users are those
-- who wrote the kept versions, the kept associations, or whose profile is kept; their profile
-- (which is a document, with a history) is kept in turn, hence the loop.
create table devdb.keep_version (id integer primary key);
create table devdb.keep_user (user_id integer primary key);

create function devdb.select_versions_and_users() returns void language plpgsql as $$
declare
  added integer;
begin
  loop
    truncate devdb.keep_version, devdb.keep_user;

    insert into devdb.keep_version
      select v.id
      from guidebook.documents_versions v join devdb.keep_doc k using (document_id)
      where k.reason like 'edge:%' or (v.document_id % 100) < devdb.p('history_sample_pct')::int
      union
      (select distinct on (v.document_id, v.lang) v.id
       from guidebook.documents_versions v join devdb.keep_doc k using (document_id)
       order by v.document_id, v.lang, v.id desc);

    insert into devdb.keep_user
      select h.user_id
      from devdb.keep_version kv
      join guidebook.documents_versions v on v.id = kv.id
      join guidebook.history_metadata h on h.id = v.history_metadata_id
      union
      select l.user_id
      from guidebook.association_log l
      join devdb.keep_doc p on p.document_id = l.parent_document_id
      join devdb.keep_doc c on c.document_id = l.child_document_id
      union
      select u.id
      from users.user u join devdb.keep_doc k on k.document_id = u.id;

    insert into devdb.keep_doc
      select p.document_id, 'profile-of-author'
      from devdb.keep_user u join guidebook.user_profiles p on p.document_id = u.user_id
      on conflict do nothing;
    get diagnostics added = row_count;

    exit when added = 0;
  end loop;
end
$$;
select devdb.select_versions_and_users();

select split_part(reason, ':', 1) as reason, count(*) from devdb.keep_doc group by 1 order by 2 desc;
select d.type, count(*) from devdb.keep_doc k join guidebook.documents d using (document_id) group by 1 order by 2 desc;
select (select count(*) from devdb.keep_version) as versions, (select count(*) from devdb.keep_user) as users;
