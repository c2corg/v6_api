-- Last checks before the dump: fails (and so does the build) if personal data is left.
-- The integrity of the references is checked by the creation of the foreign keys, which is done
-- on the final data.

do $$
declare
  n bigint;
  t text;
  c text;
begin
  -- users: nothing real left, and a single known password
  select count(*) into n from users.user where email not like '%@example.com';
  if n > 0 then raise exception '% users have a real email', n; end if;
  select count(*) into n from users.user
    where password <> '$2b$12$JPOxvA1AUc4LRUE6OJMlLeFoKoTYjfGpnBsC4tSE7VhAh3e/AmeGi';
  if n > 0 then raise exception '% users have a real password', n; end if;
  select count(*) into n from users.user where email_to_validate is not null or validation_nonce is not null;
  if n > 0 then raise exception '% users have a pending validation', n; end if;

  -- tables that must be empty
  foreach t in array array[
    'users.token', 'users.sso_external_id', 'users.sso_key', 'sympa.subscriber_table',
    'tracking.users', 'tracking.activities', 'tracking.polar', 'tracking.strava',
    'guidebook.feed_followed_users', 'guidebook.feed_filter_area', 'guidebook.documents_tags',
    'guidebook.documents_tags_log', 'guidebook.documents_topics', 'guidebook.es_deleted_documents',
    'guidebook.es_deleted_locales'
  ] loop
    execute format('select count(*) from %s', t) into n;
    if n > 0 then raise exception '% still contains % rows', t, n; end if;
  end loop;

  -- free texts that must be lorem ipsum (same expression as in anonymize-data.sql)
  foreach t in array array['guidebook.xreports_locales', 'guidebook.xreports_locales_archives'] loop
    foreach c in array array[
      'place', 'route_study', 'conditions', 'training', 'motivations', 'group_management', 'risk',
      'time_management', 'safety', 'reduce_impact', 'increase_impact', 'modifications', 'other_comments'
    ] loop
      execute format(
        'select count(*) from %1$s where %2$I is distinct from left(repeat(%3$L, length(%2$I) / 57 + 1), length(%2$I))',
        t, c, 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. ') into n;
      if n > 0 then raise exception '%.% has % texts which are not lorem ipsum', t, c, n; end if;
    end loop;
  end loop;
  foreach t in array array['guidebook.outings_locales', 'guidebook.outings_locales_archives'] loop
    execute format(
      'select count(*) from %1$s where participants is distinct from left(repeat(%2$L, length(participants) / 57 + 1), length(participants))',
      t, 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. ') into n;
    if n > 0 then raise exception '%.participants has % texts which are not lorem ipsum', t, n; end if;
  end loop;

  select count(*) into n from guidebook.documents_locales
    where type = 'x' and (summary is not null or description is not null)
      and (summary is distinct from left(repeat('Lorem ipsum dolor sit amet, consectetur adipiscing elit. ', length(summary) / 57 + 1), length(summary))
        or description is distinct from left(repeat('Lorem ipsum dolor sit amet, consectetur adipiscing elit. ', length(description) / 57 + 1), length(description)));
  if n > 0 then raise exception '% xreports locales are not lorem ipsum', n; end if;

  -- profiles: nothing but the existence
  select count(*) into n from guidebook.user_profiles where activities is not null or categories is not null;
  if n > 0 then raise exception '% profiles have personal data', n; end if;
  select count(*) into n from guidebook.documents_locales l join guidebook.user_profiles p using (document_id)
    where l.summary is not null or l.description is not null;
  if n > 0 then raise exception '% profiles have a description', n; end if;
end
$$;

-- Summary
select 'documents' as what, count(*) from guidebook.documents
union all select 'users', count(*) from users.user
union all select 'versions', count(*) from guidebook.documents_versions
union all select 'stopareas', count(*) from guidebook.stopareas
union all select 'associations', count(*) from guidebook.associations;
