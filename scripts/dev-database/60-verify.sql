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

-- Names, contact details and mentions (same patterns and columns as in anonymize-data.sql)
do $$
declare
  n bigint;
  t text;
  c text;
  email constant text := '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}';
  mention constant text := '(^|[^A-Za-z0-9._%+-])@[A-Za-z_]';
  phone constant text := '(\+|\y00)[0-9]{2}[ .-]?(\(0\)|0)?[ .-]?[0-9]{1,3}([ .-]?[0-9]{2,4}){2,4}|\y0[1-9]([ .-]?[0-9]{2}){4}\y';
begin
  -- the accounts for the developers exist, and nobody can log in as the former member
  select count(*) into n from users.user where username in ('moderator', 'user', 'blocked', 'unvalidated') and id > 0;
  if n <> 4 then raise exception '% test accounts instead of 4', n; end if;
  select count(*) into n from users.user where id = -1 and (moderator or not blocked or email_validated);
  if n > 0 then raise exception 'the former member can log in or moderate'; end if;

  -- a name is a pseudonym (a single word) or `User <id>`: any space or @ may be an identity or an email
  select count(*) into n from users.user
    where id <> -1 and name !~ '^User [0-9]+$' and name ~ '[[:space:]@]';
  if n > 0 then raise exception '% users have a name which may be an identity', n; end if;

  foreach t in array array['guidebook.images', 'guidebook.images_archives'] loop
    execute format('select count(*) from %s where author <> '''' and author !~ ''^Author [0-9]+$''', t) into n;
    if n > 0 then raise exception '% still has % real image authors', t, n; end if;
  end loop;

  foreach t in array array['guidebook.waypoints', 'guidebook.waypoints_archives'] loop
    foreach c in array array['phone', 'phone_custodian'] loop
      execute format('select count(*) from %1$s where %2$I <> '''' and %2$I <> ''00 00 00 00 00''', t, c) into n;
      if n > 0 then raise exception '%.% has % real phone numbers', t, c, n; end if;
    end loop;
  end loop;

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
    union all select 'guidebook.history_metadata', 'comment'
  loop
    -- fake emails (and the ones which already were examples) are fine
    execute format('select count(*) from %1$s where regexp_replace(%2$I, ''[A-Za-z0-9._%%+-]+@example\.com'', '''', ''g'') ~* %3$L', t, c, email) into n;
    if n > 0 then raise exception '%.% has % emails', t, c, n; end if;
    execute format('select count(*) from %1$s where regexp_replace(%2$I, ''@(user|example\.com)'', '''', ''g'') ~ %3$L', t, c, mention) into n;
    if n > 0 then raise exception '%.% has % mentions of users', t, c, n; end if;
    execute format('select count(*) from %1$s where regexp_replace(%2$I, ''00 00 00 00 00'', '''', ''g'') ~ %3$L', t, c, phone) into n;
    if n > 0 then raise exception '%.% has % phone numbers', t, c, n; end if;
  end loop;
end
$$;

-- Summary
select 'documents' as what, count(*) from guidebook.documents
union all select 'users', count(*) from users.user
union all select 'versions', count(*) from guidebook.documents_versions
union all select 'stopareas', count(*) from guidebook.stopareas
union all select 'associations', count(*) from guidebook.associations;
