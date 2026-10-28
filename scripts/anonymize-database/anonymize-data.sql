\connect c2corg

-- This file contains SQL queries used to remove personal data before exporting the database to a public dump

-- Replaces a free text by a lorem ipsum of the same length: NULL stays NULL, empty stays empty, and the
-- length distribution is preserved (so that layout edge cases remain testable) without keeping any content.
create function pg_temp.lorem(t text) returns text language sql immutable as $$
  select left(repeat('Lorem ipsum dolor sit amet, consectetur adipiscing elit. ', length(t) / 57 + 1), length(t))
$$;

-- Replaces the emails, the phone numbers and the @mentions of users found in a free text by fake ones.
create function pg_temp.scrub(t text) returns text language sql immutable as $$
  select regexp_replace(regexp_replace(
    regexp_replace(t, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', 'email@example.com', 'g'),
    '(^|[^A-Za-z0-9._%+-])@[A-Za-z0-9_][A-Za-z0-9_.-]*', '\1@user', 'g'),
    '(\+|\y00)[0-9]{2}[ .-]?(\(0\)|0)?[ .-]?[0-9]{1,3}([ .-]?[0-9]{2,4}){2,4}|\y0[1-9]([ .-]?[0-9]{2}){4}\y', '00 00 00 00 00', 'g')
$$;

-- Replace users'data by fake data. The name is the one displayed to everybody (history of the documents, authors
-- of the outings...): it is kept for the users whose profile is public, unless it looks like a real identity (an email, or
-- "Firstname Lastname"), and replaced by `User <id>` for everybody else. The `is_profile_public` flag is kept.
-- password = c2c
update users.user set username = 'user' || id, forum_username = 'user' || id, email = 'user' || id || '@example.com', email_validated = true, email_to_validate = null, moderator = false, validation_nonce = null, validation_nonce_expire = null, password = '$2b$12$JPOxvA1AUc4LRUE6OJMlLeFoKoTYjfGpnBsC4tSE7VhAh3e/AmeGi', last_modified = now(), lang = 'en', feed_filter_activities = '{}', feed_followed_only = false,  blocked = false, feed_filter_langs = '{}', name = case when is_profile_public and name !~ '@' and name !~ '^[A-ZÀ-Ý][a-zà-ÿ-]+( [A-ZÀ-Ý][a-zà-ÿ-]+)+$' then name else 'User ' || id end, tos_validated = now(), ratelimit_remaining = null, ratelimit_reset = null, ratelimit_last_blocked_window = null, ratelimit_times = 0;

-- Remove all authentication data
truncate users.token, users.sso_external_id, users.sso_key;

-- Remove all snow reports subscriptions
truncate sympa.subscriber_table;

-- Remove personal data in xreports
update guidebook.xreports set author_status = null, activity_rate = null, age = null, gender = null, previous_injuries = null, autonomy = null, supervision = null, qualification = null;
update guidebook.xreports_archives set author_status = null, activity_rate = null, age = null, gender = null, previous_injuries = null, autonomy = null, supervision = null, qualification = null;

-- Replace the free text of xreports (accident narratives, which may name people) by lorem ipsum
update guidebook.xreports_locales set place = pg_temp.lorem(place), route_study = pg_temp.lorem(route_study), conditions = pg_temp.lorem(conditions), training = pg_temp.lorem(training), motivations = pg_temp.lorem(motivations), group_management = pg_temp.lorem(group_management), risk = pg_temp.lorem(risk), time_management = pg_temp.lorem(time_management), safety = pg_temp.lorem(safety), reduce_impact = pg_temp.lorem(reduce_impact), increase_impact = pg_temp.lorem(increase_impact), modifications = pg_temp.lorem(modifications), other_comments = pg_temp.lorem(other_comments);
update guidebook.xreports_locales_archives set place = pg_temp.lorem(place), route_study = pg_temp.lorem(route_study), conditions = pg_temp.lorem(conditions), training = pg_temp.lorem(training), motivations = pg_temp.lorem(motivations), group_management = pg_temp.lorem(group_management), risk = pg_temp.lorem(risk), time_management = pg_temp.lorem(time_management), safety = pg_temp.lorem(safety), reduce_impact = pg_temp.lorem(reduce_impact), increase_impact = pg_temp.lorem(increase_impact), modifications = pg_temp.lorem(modifications), other_comments = pg_temp.lorem(other_comments);
update guidebook.documents_locales set summary = pg_temp.lorem(summary), description = pg_temp.lorem(description) where type = 'x';
update guidebook.documents_locales_archives set summary = pg_temp.lorem(summary), description = pg_temp.lorem(description) where type = 'x';

-- Replace the list of participants of outings (free text, usually real names) by lorem ipsum
update guidebook.outings_locales set participants = pg_temp.lorem(participants);
update guidebook.outings_locales_archives set participants = pg_temp.lorem(participants);

-- Remove personal data in profiles
update guidebook.user_profiles set activities = null, categories = null;
update guidebook.documents_locales set summary = null, description = null where document_id in (select document_id from guidebook.user_profiles);
update guidebook.documents_geometries set geom = null, geom_detail = null where document_id in (select document_id from guidebook.user_profiles);

-- Remove archived profiles as well
update guidebook.user_profiles_archives set activities = null, categories = null;
update guidebook.documents_locales_archives set summary = null, description = null where document_id in (select distinct d.document_id from guidebook.user_profiles_archives p join guidebook.documents_archives d using (id));
update guidebook.documents_geometries_archives set geom = null, geom_detail = null where document_id in (select distinct d.document_id from guidebook.user_profiles_archives p join guidebook.documents_archives d using (id));

-- Remove user subscriptions, bookmarks and preferences
truncate guidebook.feed_followed_users, guidebook.feed_filter_area, guidebook.documents_tags, guidebook.documents_tags_log;

-- Remove ES indexing related data
truncate guidebook.es_deleted_documents, guidebook.es_deleted_locales, guidebook.es_sync_status;
insert into guidebook.es_sync_status VALUES (to_timestamp(0), 1);

-- remove tracking data
truncate tracking.users, tracking.activities, tracking.polar, tracking.strava;

-- Pseudonymize the author of the images (free text, usually a real name)
create temp table image_authors as
  select author, row_number() over (order by author) as n
  from (select author from guidebook.images where author <> ''
        union select author from guidebook.images_archives where author <> '') a;
update guidebook.images i set author = 'Author ' || a.n from image_authors a where i.author = a.author;
update guidebook.images_archives i set author = 'Author ' || a.n from image_authors a where i.author = a.author;

-- Replace the phone numbers of the custodians (people) of huts, campsites... by a fake one
update guidebook.waypoints set phone = '00 00 00 00 00' where phone <> '';
update guidebook.waypoints set phone_custodian = '00 00 00 00 00' where phone_custodian <> '';
update guidebook.waypoints_archives set phone = '00 00 00 00 00' where phone <> '';
update guidebook.waypoints_archives set phone_custodian = '00 00 00 00 00' where phone_custodian <> '';

-- Remove the emails, the phone numbers and the @mentions which people wrote in the free texts
do $$
declare
  t text;
  c text;
begin
  for t, c in
    select tbl || suffix, col
    from (values
      ('guidebook.documents_locales', 'title'), ('guidebook.documents_locales', 'summary'), ('guidebook.documents_locales', 'description'),
      ('guidebook.waypoints_locales', 'access'), ('guidebook.waypoints_locales', 'access_period'), ('guidebook.waypoints_locales', 'external_resources'),
      ('guidebook.routes_locales', 'slope'), ('guidebook.routes_locales', 'remarks'), ('guidebook.routes_locales', 'gear'),
      ('guidebook.routes_locales', 'external_resources'), ('guidebook.routes_locales', 'route_history'),
      ('guidebook.routes_locales', 'slackline_anchor1'), ('guidebook.routes_locales', 'slackline_anchor2'),
      ('guidebook.outings_locales', 'access_comment'), ('guidebook.outings_locales', 'weather'), ('guidebook.outings_locales', 'timing'),
      ('guidebook.outings_locales', 'conditions_levels'), ('guidebook.outings_locales', 'conditions'), ('guidebook.outings_locales', 'avalanches'),
      ('guidebook.outings_locales', 'hut_comment'), ('guidebook.outings_locales', 'route_description')
    ) as v(tbl, col)
    cross join (values (''), ('_archives')) as s(suffix)
  loop
    execute format('update %1$s set %2$I = pg_temp.scrub(%2$I) where %2$I is distinct from pg_temp.scrub(%2$I)', t, c);
  end loop;
end
$$;
update guidebook.history_metadata set comment = pg_temp.scrub(comment) where comment is distinct from pg_temp.scrub(comment);
