-- This file contains SQL queries used to remove personal data before exporting the database to a public dump

-- Replace users'data by fake data. Except (real) name to preserve the authors of the guidebook contributions.
-- password = c2c
update users.user set username = 'user' || id, forum_username = 'user' || id, email = 'user' || id || '@example.com', email_validated = true, email_to_validate = null, moderator = false, validation_nonce = null, validation_nonce_expire = null, password = '$2b$12$JPOxvA1AUc4LRUE6OJMlLeFoKoTYjfGpnBsC4tSE7VhAh3e/AmeGi', last_modified = now(), lang = 'en', is_profile_public = false, feed_filter_activities = '{}', feed_followed_only = false,  blocked = false, feed_filter_langs = '{}';

-- Remove all authentication data
truncate users.token, users.sso_external_id, users.sso_key;

-- Remove all snow reports subscriptions
truncate sympa.subscriber_table;

-- Remove personal data in xreports
update guidebook.xreports set author_status = null, activity_rate = null, nb_outings = null, age = null, gender = null, previous_injuries = null, autonomy = null;
update guidebook.xreports_archives set author_status = null, activity_rate = null, nb_outings = null, age = null, gender = null, previous_injuries = null, autonomy = null;

-- Remove personal data in profiles
update guidebook.user_profiles set activities = null, categories = null;
update guidebook.documents_locales set summary = null, description = null where document_id in (select document_id from guidebook.user_profiles);
update guidebook.documents_geometries set geom = null, geom_detail = null where document_id in (select document_id from guidebook.user_profiles);

-- Remove archived profiles as well
update guidebook.user_profiles_archives set activities = null, categories = null;
update guidebook.documents_locales_archives set summary = null, description = null where document_id in (select distinct d.document_id from guidebook.user_profiles_archives p join guidebook.documents_archives d using (id));
update guidebook.documents_geometries_archives set geom = null, geom_detail = null where document_id in (select distinct d.document_id from guidebook.user_profiles_archives p join guidebook.documents_archives d using (id));

-- Remove user subscriptions and preferences
truncate guidebook.feed_followed_users, guidebook.feed_filter_area;

-- Remove ES indexing related data
truncate guidebook.es_deleted_documents, guidebook.es_deleted_locales, guidebook.es_sync_status;
