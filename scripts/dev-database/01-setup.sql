-- Working objects of the dev database build. The whole devdb schema is dropped before the dump.
--
-- Everything is tunable from here: the zones that are kept entirely, and the sampling parameters.

set work_mem = '256MB';

drop schema if exists devdb cascade;
create schema devdb;

-- Areas (guidebook.areas) whose content is kept. Their waypoints, routes, outings are kept, and
-- the other documents attached to them are pulled in by the closure (see 10-select.sql).
-- Chosen to cover: Navitia-rich French Alps, a Swiss area (no stopareas at all), the Pyrenees on
-- the Spanish border (ES / CA locales), with a good amount of xreports and several langs.
create table devdb.zone (area_id integer primary key, label text not null);
insert into devdb.zone values
  (14398, 'Belledonne (FR Alps)'),
  (14401, 'Chartreuse (FR Alps, many stopareas)'),
  (14437, 'Valais W - Alpes Pennines W (CH, no stopareas)'),
  (14412, 'Luchon - Posets - Maladeta - Aiguestortes (FR/ES Pyrenees)');

create table devdb.params (name text primary key, value text not null);
insert into devdb.params values
  ('outing_since', '2024-01-01'),  -- outings of the zones at least this recent are kept...
  ('outing_sample_pct', '3'),      -- ...plus this percentage of the older ones (deterministic, by id)
  ('history_sample_pct', '2'),     -- percentage of documents which keep their whole version history
  ('history_max_versions', '30'), -- but at most this many (the last ones) per document and lang
  ('edge_per_rule', '8'),          -- documents kept per edge case rule (see 10-select.sql)
  ('images_per_document', '6');    -- max number of images kept per parent document

create function devdb.p(name text) returns text language sql stable as $$
  select value from devdb.params where name = $1
$$;

-- Documents that are kept (with the reason why, to be able to audit the selection)
create table devdb.keep_doc (document_id integer primary key, reason text not null);

-- Keeps in a table only the rows matching a predicate. Truncating and re-inserting avoids the dead
-- tuples of a huge DELETE (and the disk space and VACUUM it would need).
create function devdb.shrink(t regclass, pred text) returns void language plpgsql as $$
declare
  before_rows bigint;
  after_rows bigint;
begin
  execute format('select count(*) from %s', t) into before_rows;
  execute format('create table devdb.shrink_tmp as select * from %s where %s', t, pred);
  execute format('truncate %s', t);
  execute format('insert into %s select * from devdb.shrink_tmp', t);
  drop table devdb.shrink_tmp;
  execute format('select count(*) from %s', t) into after_rows;
  raise notice '%: % -> % rows', t, before_rows, after_rows;
end
$$;
