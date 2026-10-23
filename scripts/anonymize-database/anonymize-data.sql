\connect c2corg

-- This file contains SQL queries used to remove personal data before exporting the database to a public dump

-- Replaces a free text by a lorem ipsum of the same length: NULL stays NULL, empty stays empty, and the
-- length distribution is preserved (so that layout edge cases remain testable) without keeping any content.
create function pg_temp.lorem(t text) returns text language sql immutable as $$
  select left(repeat('Lorem ipsum dolor sit amet, consectetur adipiscing elit. ', length(t) / 57 + 1), length(t))
$$;

-- Replace users'data by fake data. Except (real) name to preserve the authors of the guidebook contributions.
-- password = c2c
update users.user set username = 'user' || id, forum_username = 'user' || id, email = 'user' || id || '@example.com', email_validated = true, email_to_validate = null, moderator = false, validation_nonce = null, validation_nonce_expire = null, password = '$2b$12$JPOxvA1AUc4LRUE6OJMlLeFoKoTYjfGpnBsC4tSE7VhAh3e/AmeGi', last_modified = now(), lang = 'en', is_profile_public = false, feed_filter_activities = '{}', feed_followed_only = false,  blocked = false, feed_filter_langs = '{}', tos_validated = now(), ratelimit_remaining = null, ratelimit_reset = null, ratelimit_last_blocked_window = null, ratelimit_times = 0;

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
