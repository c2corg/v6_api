BEGIN;


ALTER TABLE punbb_users DROP constraint IF EXISTS unique_username;
ALTER TABLE punbb_users DROP constraint IF EXISTS valid_username;
alter table app_users_private_data drop constraint IF EXISTS unique_user_login_name;

-- Append _dup to duplicated login names and add unique constraint
update app_users_private_data set login_name = login_name || '_dup' where id in (select min(id) from app_users_private_data group by login_name having count(login_name) >= 2);
alter table app_users_private_data add constraint unique_user_login_name unique(login_name);



-- Rename username column to old_username column
ALTER TABLE punbb_users RENAME COLUMN username TO old_username;


-- Add a username column with normalized old_username for Discourse and constraints
ALTER TABLE punbb_users ADD COLUMN  username varchar(15);

-- Initially populate with unaccented alphanumeric old_username truncated to 15 characters
update punbb_users set username = substring(regexp_replace(unaccent(old_username), '[^a-zA-Z0-9]', '', 'g'), 0, 16);

-- Create and call a normalizing function which will update the username column for conflicting rows
-- sss is appended to short old_usernames. d + a figure is appended to duplicate old_usernames. Only keep first 13 characters.
CREATE OR REPLACE FUNCTION normalize() RETURNS integer AS
$PROC$
    DECLARE
        r RECORD;
        i integer;
        changed integer;
    BEGIN
        changed = 0;
        FOR r IN
          -- Discourse allows 15 characters. We only take 13 characters in order to have enough extra space for adding a unique suffix.
          select count(*) count, sort(int_array_aggregate(punbb_users.id)) AS ids, substring(regexp_replace(unaccent(old_username), '[^a-zA-Z0-9]', '', 'g'), 0, 14) AS basename
          FROM punbb_users GROUP BY basename HAVING (count(*) > 1 or length(substring(regexp_replace(unaccent(old_username), '[^a-zA-Z0-9]', '', 'g'), 0, 14)) < 3) ORDER BY count(*) DESC
        LOOP
          FOR i IN 1 .. array_length(r.ids, 1)
          LOOP
            IF length(r.basename) < 3
            THEN
              -- append shorter names with three sss
              r.basename = r.basename || 'sss';
            END IF;

            update punbb_users set username = r.basename || 'd' || i::text where punbb_users.id = r.ids[i];
            changed = changed + 1;
          END LOOP;
        END LOOP;
        RETURN changed;
    END;
$PROC$ LANGUAGE plpgsql;
select normalize();

-- Add non null, unique and check constraints to the username column
ALTER TABLE punbb_users ALTER COLUMN username SET NOT NULL;
ALTER TABLE punbb_users ADD constraint unique_username unique(username);
ALTER TABLE punbb_users ADD constraint valid_username CHECK(char_length(username) >= 3 and char_length(username) <= 15 and username !~ '.*[^a-zA-Z0-9]+.*');

-- Set not null on topo_name
alter table app_users_private_data alter column topo_name set not null;


-- Count modified usernames
select count(*) from punbb_users where old_username != username;


-- Commit the changes if no error occured
DROP FUNCTION normalize();
COMMIT;
