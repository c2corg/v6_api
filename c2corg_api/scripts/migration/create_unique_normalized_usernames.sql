
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION check_forum_username(name TEXT)
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

  IF name ~ '[^\w.-]' THEN
    RETURN FALSE;
  END IF;

  IF left(name, 1) ~ '\W' THEN
    RETURN FALSE;
  END IF;

  IF right(name, 1) ~ '[^A-Za-z0-9]' THEN
    RETURN FALSE;
  END IF;

  IF name ~ '[-_\.]{2,}' THEN
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


CREATE OR REPLACE FUNCTION normalize_username(username TEXT, id INTEGER)
RETURNS text AS $$
DECLARE
  s TEXT;
BEGIN
  s := unaccent(username);

  s := regexp_replace(s, '[\s@&:/]+', '_', 'g');
  s := regexp_replace(s, '[''*]+', '.', 'g');
  s := regexp_replace(s, 'ø+', '0', 'g');
  s := regexp_replace(s, '\$+', 'S', 'g');

  -- remove consecutive special characters
  s := regexp_replace(s, '[-_\.]{2,}', '', 'g');

  -- remove invalid first characters
  s := regexp_replace(s, '^\W+', '', 'g');

  -- remove invalid last characters
  s := regexp_replace(s, '[^A-Za-z0-9]+$', '', 'g');

  -- remove all invalid characters
  s := regexp_replace(s, '[^\w.-]+', '', 'g');

  -- remove confusin suffixes
  s := regexp_replace(s, '\.(js|json|css|htm|html|xml|jpg|jpeg|png|gif|bmp|ico|tif|tiff|woff)$', '', 'g');

  -- if len < 3 complete with user id
  IF char_length(s) < 3 THEN
    s := s || id::text;
  END IF;

  -- cut at 25 characters
  s := left(s, 25);

  RETURN s;
END;
$$ LANGUAGE plpgsql;


/*
 * Create column username_normalized
 */
ALTER TABLE punbb_users ADD COLUMN username_normalized varchar(25);

ALTER TABLE punbb_users
  ADD CONSTRAINT username_normalized_check_constraint CHECK (check_forum_username(username_normalized::text));

UPDATE punbb_users SET username_normalized = normalize_username(normalize_username(username, id), id);


/*
 * Create column username_unique
 */
ALTER TABLE punbb_users ADD COLUMN username_unique varchar(25);

ALTER TABLE punbb_users
  ADD CONSTRAINT username_unique_check_constraint CHECK (check_forum_username(username_unique::text));

CREATE UNIQUE INDEX ix_punbb_users_lower_username_unique
  ON punbb_users
  USING btree
  (lower(username_unique::text) COLLATE pg_catalog."default");

UPDATE punbb_users
SET username_unique = substring(username_normalized from 1 for  24) || number
FROM (
  SELECT
    id,
    row_number() OVER (PARTITION BY lower(username_normalized) ORDER BY id) AS number
  FROM
    punbb_users
) AS indexed
WHERE punbb_users.id = indexed.id
AND number > 1


/*
 * Visual control
 */
SELECT
    username,
    username_unique
FROM punbb_users
WHERE username_unique != username;


/*
 * Apply on punbb_users.username
 */
UPDATE punbb_users
SET username = username_unique;
