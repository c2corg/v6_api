# Partner outings

The `/metaskirando` view of the UI shows, next to the outings of Camptocamp, the outings reported on partner
sites ([skitour.fr](https://skitour.fr), [gulliver.it](https://www.gulliver.it), [bivouak.net](https://www.bivouak.net)
[gipfelbuch.ch](https://www.gipfelbuch.ch), [skitourenportal.eu](https://skitourenportal.eu) and
[on-ice.it](http://www.on-ice.it/onice/), all on by default). The API does not proxy the partner sites
at request time: the harvester of [docs/harvest.md](harvest.md) runs each source every 15 minutes into its own tables,
and `GET /partner-outings` merges those rows with the c2c outings of the same period.

```
harvest_tick (c2corg_api/harvest) -> PartnerHarvester partners.<name> (jobs/harvest_partner_outings.py)
  -> adapter (c2corg_api/partners/sources/<name>.py, pure) -> run_source: upsert, areas, health
  -> guidebook.partner_outings / partner_sources / partner_lookups (+ harvest_sources: schedule, errors)
  -> GET /partner-outings, GET /partner-outings/sources (views/partner_outings.py), GET /health (harvest)
```

- An adapter only turns the answers of the site into `HarvestedOuting` objects. It gets its HTTP transport and its
  lookup cache from the job, so it runs unchanged on recorded fixtures.
- Each adapter is a harvester of the shared framework (`c2corg_api/harvest`, [docs/harvest.md](harvest.md)), named
  `partners.<name>` with one source (`partners.skitour:outings`): the harvest tick schedules it, the policy backs it
  off after errors, `harvest_sources` keeps its schedule and errors, and `/health` reports it under `harvest`.
- The job locates the outings published without coordinates from their hints (summit name, region, country: see
  [Outings without coordinates](#outings-without-coordinates)), stores the rows (one per source and external id),
  assigns the c2c areas that contain the point of each outing, records the health of each source, and a second job purges
  the lookups older than their retention (`partner_lookups` is a cache of the partner sites, not data).
- **Kept forever.** By default (`partners_retention=""`) no outing and no GPX track is ever purged: there is no 31-day
  (or any) retention. The 31 days are only the widest window of one `GET /partner-outings` query (and of the UI), not
  how long the rows live. Setting `partners_retention` is the only way to have the purge job delete outings (and, by
  cascade, their tracks); that purge job is scheduled even when the harvest is off.
- **Stored, never served.** A partner outing row also keeps `texts`: the free texts of the report (plain text, keyed by
  kind: `narrative`, `conditions`, `access`, `snow`, `equipment`; `TEXT_KINDS` in `partners/model.py`), for later uses
  (search, statistics) under the partners' agreement. They are never in an answer of the API (`GET /partner-outings`
  selects its columns, a test checks no text leaks), and never real in a fixture (see the recording). `gpx_url` is the
  link to the public GPX file of the report (gulliver.it: its first track); the points of the file are read by a slower
  second phase ([GPX tracks](#gpx-tracks)).
- **Backfill.** The harvest only reads the latest reports. Importing the history of a site is not done
  ([c2corg/v6_api#2763](https://github.com/c2corg/v6_api/issues/2763)); the design allows it: rows are upserted by
  `(source, external_id)`, kept forever by default, and an adapter can page further back with a wider `since`.
- The design is in `doc/meta/A2_HARVESTER.md` of c2corg/metaskirando-archive.
- Diagram: [partner outings](https://c2corg.github.io/v6_api/architecture/metaskirando.html) (the job, the tables,
  the API, and each partner site), linked from the [background jobs](https://c2corg.github.io/v6_api/architecture/batch.html).

## Integration points

How the job reaches each site (`partners/sources/<name>.py`; delay and budget are the `rate` of the adapter, a spent
budget makes the run `down`). Every request carries our User-Agent.

| Source | Interface | Requests of a run | Delay, budget | Position |
| --- | --- | --- | --- | --- |
| skitour.fr | JSON API `https://skitour.fr/api/sorties` (`c=1&l=200&j=<days>&p=<page>`), header `cle: $SKITOUR_API_KEY` | pages of 200 outings | 1.1 s, 10 | coordinates in the answer |
| gulliver.it | WordPress REST JSON `wp-json/gulliver/`: `mobile/commentglobal?page=1..5`, `mobile/comments?id=` (≤ 15), `mobile/routes?id=` (≤ 24 new, cached); the HTML fragment `front_page/comments?sorting=id` for the reports the paging misses | 5 + 1 + 15 + 24 at most | 2 s, 45 | start point of the route; Cloudflare challenge from datacenter addresses (`blocked`) |
| gulliver.it GPX | public `https://` `.gpx` files on gulliver.it (`gpx_url`), second phase `jobs/partner_tracks.py` | `partners.tracks_per_run` (3) | `partners.tracks_interval_seconds` (10 s at least) | the track, in `partner_tracks` |
| bivouak.net | HTML scraping: `topos/liste_des_sorties.php?id_sport=1\|2\|8\|4\|16`, then `sortie-<id>-*.html` detail pages (≤ 10 new, cached) | 5 + 10 | 10 s (`robots.txt`), 15 | `data-lat`/`data-lng` of the detail page, else hints |
| gipfelbuch.ch | HTML scraping: `/verhaeltnisse/uebersicht`, then the page of a report for its map, once per summit (≤ 15 new, cached) | 1 + 15 (+ 2 spare) | 2 s, 18 | `data-lat`/`data-lon` of the map, else hints |
| skitourenportal.eu | HTML scraping: the portal pages of 5 Austrian states (`/salzburg`...), 2 pages each (`?page=2`); no detail page | 10 at most | 3 s, 12 | map markers of the pages, else region (`regions/skitourenportal.json`) and hints |
| on-ice.it | HTML scraping over plain `http`, ISO-8859-1: `onice_reports.php?type=0` (+ the second page while new), `onice_view_report.php?type=&id=` detail pages (≤ 15 new, cached) | 2 + 15 | 2 s, 17 | none on the site: hints only |

## Configuration

Non-secret settings: `config/env.default`, overridden for the dev stack in `config/env.dev`, rendered in
`common.ini` (`make load-env`).

| env key | ini key | default | meaning |
| --- | --- | --- | --- |
| `harvest_partners_enabled` | `harvest.partners.enabled` | `true` (`false` in `env.test`) | the scheduler harvests the partner sources, whatever `harvest.enabled`; `make harvest-partners` refuses to run unless a source is on or `--force` is given |
| `harvest_partners_<name>_enabled` | `harvest.partners.<name>.enabled` | empty (all the sources on) | one source: `true`/`false`, empty as `harvest.partners.enabled` (absent is empty). skitour without `SKITOUR_API_KEY` is `disabled` (not an error) |
| `partners_interval` | `partners.interval_minutes` | `15` | minutes between two runs of a source (its harvest policy); base of the backoff |
| `partners_retention` | `partners.retention_days` | empty | empty or `0` (the default): the outings and their tracks are kept forever, nothing is purged (a query of the API lists 31 days at most: a display window, not a retention). Set: outings older than that many days are not stored, and purged with their tracks |
| `partners_lookup_retention` | `partners.lookup_retention_days` | `30` | `partner_lookups` rows (cached route, detail and summit lookups, and the job's resolutions of location hints: a cache, not data) older than that are purged |
| `partners_tracks_per_run` | `partners.tracks_per_run` | `3` | GPX tracks read after the outings of a run (`0`: none); see [GPX tracks](#gpx-tracks) |
| `partners_tracks_interval` | `partners.tracks_interval_seconds` | `10` | seconds between two GPX files (10 at least) |
| `partners_transport` | `partners.transport` | `http` (`fixtures` in `env.dev`) | `http`: the real sites; `fixtures`: recorded answers, no network |
| `partners_fixtures_dir` | `partners.fixtures_dir` | empty | empty: `c2corg_api/tests/partners/fixtures` |
| `partners_allow_synthetic` | `partners.allow_synthetic` | `false` (`true` in `env.dev` only) | fixture mode may run on a manifest with `synthetic: true`. Otherwise the source is `failing` (ERROR log, detail says why) and nothing is stored: hand-made data can never be published by accident |

Secrets come from the environment only, never from the ini files. Each secret `NAME` is read from `$NAME`; when that
is not set, from the file named by `$NAME_FILE` (the Docker secrets convention, e.g.
`SKITOUR_API_KEY_FILE=/run/secrets/skitour_api_key`; the content is stripped of surrounding whitespace). `$NAME` wins
when both are set.

- `SKITOUR_API_KEY` or `SKITOUR_API_KEY_FILE`: the key of the skitour.fr API. Without it the source is `disabled` (`status_detail`: `SKITOUR_API_KEY not set`): not a failure, no backoff, the other sources run, `/health` stays ok. Ask skitour.fr for a key; do
  not reuse any key found in old code.
- Gulliver needs none today.
- In fixture mode no secret is needed.

## Statuses of a source

`GET /partner-outings/sources` (and `partners` in `GET /health`) tell the state of each source after its last run.

| status | meaning | counts as a failure |
| --- | --- | --- |
| `never_run` | no row yet: the job has not run since the source exists (`/partner-outings/sources` lists every known source, with or without a row) | no |
| `ok` | the run went through, nothing skipped for an error | no |
| `degraded` | the run stored its outings, but some items could not be parsed (below the failure threshold), or some lookups failed (`lookup_failed` in `last_skipped`) | no |
| `failing` | a bug, too many unparsable items (more than 3 and 10%), or a storage error: nothing stored | yes |
| `blocked` | the site refuses us: 401/403/429 or an anti-bot challenge page (Cloudflare) | yes |
| `down` | the site does not answer: 5xx, timeout, or the request budget of the run is spent | yes |
| `disabled` | the source does not run by choice: a secret is missing, or it is switched off (`status_detail` says which: `not configured`, set when the scheduler starts) | no |

A failed run (`failing`, `blocked`, `down`) is an error of its harvest source (`PartnerRunFailed`, in
`harvest_sources.last_error`): the harvest policy waits 1 x, 2 x, 4 x... the interval (at most 16 x) before trying
again. `blocked` is not `down`: a blocked source needs an agreement or an allowlisting from the
partner, retrying more often only makes it worse. `status_detail` never contains a secret.

A source that fails never stops the other sources, and its previous outings stay stored (forever, unless `partners_retention` is set).

**Lookups fail one item, not the run.** A listing page that answers 5xx or times out makes the run `down`, but a
secondary request for one outing (a gulliver route, a bivouak detail page, a gipfelbuch summit page) does not: through
`partners.lookups.LookupRequests`, the outing keeps its hints (region, summit name, country) for the job to locate,
`lookup_failed` is counted in `last_skipped`, nothing is cached (the next run asks again), and the run is `degraded`.
After 3 failures in a row the site is taken for down for the rest of the run: the remaining lookups are deferred
(`route_lookup_deferred`, `location_deferred`, `summit_lookup_deferred`). A block (`SourceBlocked`: 401/403/429,
challenge page) on a lookup still stops the run: `blocked`. In fixture mode, a page missing from the recording is a
failed lookup too.

## Outings without coordinates

Some sites give no position for some or all of their outings (gipfelbuch, skitourenportal, on-ice.it, bivouak beyond its lookup
cap), only hints in `HarvestedOuting`: `summit_name` (+ `elevation_max`), `region` and `country` (ISO alpha-2). Before
storing, the job (`c2corg_api/jobs/partner_locations.py`) resolves them, in order:

1. **Summit.** The c2c waypoints of type `summit` or `pass` (not redirected) whose title, in any locale (each part of
   `A / B` alone), has the same folded name (`c2corg_api/partners/places.py`: case, accents, `ä`/`ae`, `ß`/`ss`,
   punctuation, text in brackets and a trailing elevation ignored, `Riedberger Horn` = `Riedbergerhorn`); within
   50 m of `elevation_max` when the partner gives it; inside the c2c area of the country when it gives one
   (`partners/regions/countries.json`: ISO code -> country area). Failing that, and only with an altitude, the name
   without its generic words (`Pointe de la`, `Piz`, `Monte`, `Gr.`, `Hoher`...): `Galise` (3340 m) finds
   `Pointe de la Galise` (3343 m). Two candidates or more: no match. The outing gets the point of the waypoint,
   `geom_quality = 'summit_match'`, and the areas of that point.
2. **Region.** The region text through the table of the source (`partners/regions/<source>.json`, `region_map.lookup`):
   the centroid of its first area, `geom_quality = 'area_centroid'`, and `area_ids` from the table plus the country
   (not the areas around the centroid, which the purge does not recompute either). A `<region> - <district>` text
   (gulliver's `Piemonte - CN`) is looked up whole, then by its district, then by its region. Tables: skitourenportal
   (Bundesländer), onice and gulliver (Italian regions and provinces).
3. **Country.** No point; `area_ids` is the country area alone, so the outing is listed under its country.

Otherwise the outing has no position and no area. `geom_quality` tells the UI how far to trust the point: `summit`,
`start` and `route` are given by the partner; `summit_match` (a guess by name) and `area_centroid` are found by the job
and shown as approximate, as any unknown value.

Each resolution is cached in `partner_lookups` under the source (`resolve:summit:<folded name>|<altitude>|<country>`,
`resolve:area:<id>`), misses too, and expires with the other lookups (`partners.lookup_retention_days`): a summit added
to c2c is found within that delay. The uncached summits of a run are looked up together: one scan of the titles of the
summit and pass waypoints (the waypoints table, then the locales by their `document_id` index; when every hint has an
altitude, only the waypoints within 50 m of one), folded in Python, then the point and the country areas of the
matches only (primary key, GiST index of the areas). The names are folded in Python rather than in SQL: the databases
have no `unaccent`, and `translate()` with the accent table costs about 25 µs a title in PostgreSQL (1.4 s for the
52 000 locales of the demo database), where the scan and the Python fold take 70 ms for the 3 200 summit and pass
titles of the demo (production has about 25 times more: about 1.5 s, only on runs that meet a new summit name).

## Local demo

Fixture mode runs the real job and the real adapters on recorded answers of the partner sites, so the whole chain
works offline. The fixtures are real recordings: 30 skitour.fr outings (2026-11-25) and 124 gulliver.it reports
(2026-11-27, every activity, 34 with the start point of their route, mostly in Piedmont and the Aosta valley, 7 with a
GPX link; texts redacted, authors pseudonymised). Both sources end `ok` on the first run. When the job runs, the dates
are shifted so that the newest fixture outings are dated today. A second run of the same day asks gulliver for other
routes than the recording holds: it ends `degraded` (`3 lookups failed`), as expected offline.

With the dev stack of the README (`scripts/sandbox-up.sh`, or the dev container, with the anonymized dev
database): the sources are on by default and `config/env.dev` already has `partners_transport="fixtures"` and
`partners_allow_synthetic="true"` (the demo fixtures are real recordings now; the flag only matters for a synthetic
set).

```bash
# in the app container (docker compose ... exec app bash), from the repository
make CONFIG=config/env.devcontainer load-env   # only if the ini files predate the partners settings
uv run alembic upgrade head                    # creates the partner tables (setup.sh already does it)
make harvest-partners                          # runs the job once: skitour.fr and gulliver.it fixtures
make serve                                     # API on :6543 (already running after sandbox-up.sh)
```

`make harvest-partners` runs the enabled sources now, due or not (`harvest.runner.harvest_now`). It needs
`harvest.partners.enabled` (it exits with a message otherwise; `--force` overrides). It logs a lot of SQL; the last
lines tell the status of each source
(`Partner source skitour: degraded (10 upserted)`). Then:

```bash
curl -s 'localhost:6543/partner-outings' | python3 -m json.tool | head -60
curl -s 'localhost:6543/partner-outings?act=skitouring'
curl -s 'localhost:6543/partner-outings?steep=true'                 # ski rating 4.1+ (or global D-+)
curl -s 'localhost:6543/partner-outings?sources=gulliver'
curl -s 'localhost:6543/partner-outings?a=14409'                    # the Vanoise range of the demo database
curl -s 'localhost:6543/partner-outings?date=2026-06-18,2026-07-18&sources=c2c'   # the c2c outings of the demo database
curl -s 'localhost:6543/partner-outings/sources' | python3 -m json.tool
curl -s 'localhost:6543/health'                                      # "harvest": {"partners.skitour": {...}, ...}
```

Notes:

- The answer is `{total, items, sources}`. The default window is the last 14 days. The anonymized database
  has no recent c2c outings (the newest are months old), so the default window shows partner rows only: ask for an
  old window with `date=<from>,<to>` (31 days at most) to see c2c rows, and `sources=c2c` or `sources=skitour,gulliver`
  to select a side.
- The fixture coordinates fall in real areas of the demo database: the `areas` of each item are filled
  (country, department, range). Rows without a point (or outside any area) have `areas: []`.
- Run the job again whenever you like: it is idempotent (upsert), and shifts the dates to the current day.
  `make run-background-jobs` starts the scheduler: its harvest tick re-harvests each source every
  `partners.interval_minutes`.
- The answers are cached twice: 120 s in Redis and 120 s by the clients (`Cache-Control: max-age=120`), so a new
  harvest can take about 4 minutes to show: wait, or flush with `make flush-redis` (and reload without cache).
- Another port (the main API already uses 6543): `C2C_API_CONFIG=development.ini uv run uvicorn c2corg_api.asgi:app --port 6544`.

The UI (c2c_ui checkout, Node 22):

```bash
C2C_BACKEND=localhost npm run serve     # http://localhost:8080/metaskirando
```

### The same demo as a test

`c2corg_api/tests/jobs/test_partner_outings_e2e.py` runs the demo offline on the test database: the job with the
real adapters on the fixtures, test areas around the fixture points, c2c outings next to them, then `GET
/partner-outings`, `/partner-outings/sources` and `/health` with the filters.

```bash
uv run pytest c2corg_api/tests/jobs/test_partner_outings_e2e.py
```

## Partner API changes: recording and live checks

The partner adapters (`c2corg_api/partners/sources/`) read the JSON of third
party sites that can change without notice. Tests never call those sites: they
replay fixtures (`c2corg_api/tests/partners/fixtures/<source>/`, see the README
there). Two tools tell a maintainer when a partner changed its API, and let
them refresh the fixtures. Run them from a machine that reaches the sites.

### Re-recording the fixtures

```
python -m c2corg_api.partners record <source> [--out DIR] [--since YYYY-MM-DD]
```

`<source>` is `skitour`, `gulliver`, `bivouak`, `gipfelbuch`, `skitourenportal` or `onice`. The command runs the real adapter with
the real transport, through a `RecordingTransport`, and writes into
`<out>/<source>/` (default: the tests fixtures directory):

- the response files and `manifest.json` (`synthetic: false`, `recorded_at`
  today). The number of days asked from skitour (`j`) is not recorded, so the
  fixtures fit any `since`;
- `shape.json`: the shape (keys and value types) of every recorded JSON file,
  keyed by file name. `shapes` compares with it.

Payloads are trimmed before they are written, by an **allow-list**: only the
paths an adapter lists in its `REQUIRED_PATHS` are kept, everything else is
dropped, and lists are cut to 30 items (also the objects keyed by ids: a
`*` in a path stands for any key, `*.ID` for gulliver's `{"350636": {...}}`).
No real partner free text reaches a fixture, whatever new fields the site adds:
the texts an adapter does not read are dropped (skitour `recit`, `photos`...),
and the texts it reads to store them (`HarvestedOuting.texts`: gulliver
`content`, `meta.access`, `meta.obs`...) are listed in `REDACT_PATHS` (JSON) or
`REDACT_SELECTORS` (HTML): the recorder replaces each of them by a placeholder,
`[text 491 chars]`. The authors are pseudonymised (`PSEUDONYMISE_PATHS`). Of the
gulliver tracks only the GPX link (`tracks[].guid`) is kept. An HTML fragment
inside a JSON answer (gulliver's front page) is declared in `EMBEDDED_HTML` and
trimmed like a page. `test_fixtures_licence.py` checks the committed files: a
free-text key holds placeholders only. Secrets come from the environment
(`SKITOUR_API_KEY`) and are never written.

The recording is made aside and installed only when it succeeded: a blocked or
down site leaves the existing fixtures untouched. Review `git diff`, run the
tests, and commit. The synthetic fixtures of M1 are replaced this way, from a
machine the sites do not block.

### Sources that publish HTML (bivouak.net)

An adapter of an HTML site reads the page through CSS selectors (BeautifulSoup, `c2corg_api/partners/htmlparse.py`),
never by position, and declares them in `REQUIRED_SELECTORS` (endpoint -> selectors), next to the (empty)
`REQUIRED_PATHS`. They have the same two roles: the recorder keeps of a page only the elements they match (with their
ancestors' bare tags, no media, script or other text: the narratives of the reports never reach a fixture), and
`shapes` / the live test check that each selector that matched in the fixtures still matches. The endpoint of a URL is
its last path segment without extension and without an id (`sortie-30061-x.html` is `sortie`).
The elements holding a partner user's identity (author name and profile link) are listed in `PSEUDONYMISE_SELECTORS`:
the recorder replaces their text and the last segment of their link by `user1`, `user2`... (stable within a recording),
as `PSEUDONYMISE_PATHS` does for JSON, and `test_fixtures_licence.py` fails on any other value in a real recording.

bivouak.net: one list per sport (`liste_des_sorties.php?id_sport=1|2|8|4|16`: ski, hiking, snowshoeing, mountain
biking, paragliding; `data-sport` of a card is a bit mask, an outing can have several), then the detail page of an outing
for its coordinates (`data-lat`, `data-lng` of the map): at most 10 new detail pages per run, the sports taking turns,
each answer kept in the lookup cache (`sortie:<id>`). Outings over the cap keep the massif (`region`), the country and the
summit named in the title, and are located by the job. `robots.txt` asks the crawlers for 10 s between two requests: the
adapter waits that long (5 lists + 10 pages = 15 requests, about 2.5 minutes per run at most).

### skitourenportal.eu (HTML)

The Tourenforum of Austria (Salzburg, Oberösterreich, Niederösterreich, Kärnten, Steiermark): no API, so
`sources/skitourenportal.py` reads the five portal pages (`/salzburg`...: a table of the latest tours, 16 per page,
`?page=N`) with BeautifulSoup and CSS selectors (`c2corg_api/partners/htmlparse.py`), at most 2 pages per state and one
request per 3 s. `robots.txt` allows everything. The rows have no activity (all are `skitouring`), rating or
elevation: only title, date, author, region and link.

- **Position.** DATA_SOURCES said there were no coordinates: the table has none, but the map of each portal page lists
  a marker (latitude, longitude) per tour in an inline script. It is read when there is one (`geom_quality='route'`:
  a point of the tour, not known more precisely); a marker is also looked up on the pages of the other states. A tour
  without marker keeps `region`, `country='AT'` and, when the title ends with an elevation (`Spielmann 3027`,
  `Hochkönig 2941 m`), `summit_name` and `elevation_max`, for the job to resolve. The tour pages hold no more
  (photos, narrative, comments; `/beitrag/<id>` answers 500, `/<state>/beitrag/<id>` is the portal page again).
- **Regions to areas.** `c2corg_api/partners/regions/skitourenportal.json` maps each region text to its c2c area
  (`area_ids`: the Bundesland, `admin_limits`; `range_ids`: the ranges covering at least 15% of it) and country;
  `partners/region_map.py` (`lookup(source, text)`) reads it, ignoring case, accents and ae/oe/ue spellings. It covers
  the 5 regions of the site, nothing else (Tirol, Vorarlberg, Wien and Burgenland are not on it); the ids were read
  in the demo database on 2026-11-25, and the file's `coverage` block says how. Skitour massifs and gipfelbuch region
  codes get their own `regions/<source>.json`.
- **HTML contract.** As for bivouak.net (see "Sources that publish HTML"): `REQUIRED_SELECTORS` (the same for the 5
  portal pages: rows, title and author cells, the marker script, the next link) is the allow-list of a recording and
  the contract `shapes` and the live test check; the authors are real names, so `PSEUDONYMISE_SELECTORS` records them
  as `user1`, `user2`... (name and profile link).
- **Terms.** `/informationen` gives no licence for third parties (it only lets the avalanche services reuse the photos,
  with the source). We reuse no photo or text: title, date, author, region, position and the link, with the credit.
  Ask the Tourenforum before enabling it (see Production notes).

### on-ice.it (HTML)

The reports of [on-ice.it](http://www.on-ice.it/onice/), an old Italian PHP community site (`sources/onice.py`).

- **Pages.** One list of the latest reports of every type, newest submitted first (`onice_reports.php?type=0`, 60
  rows a page: date, title, region, height difference, author), the second page (`&u=0&start=60`) only while the
  list is new to us (a full first page whose oldest report of the period was never looked up). Then the detail page
  of each new report (`onice_view_report.php?type=<type>&id=<id>`): elevation of the arrival (`Quota arrivo`, MTB
  `Quota massima`), grade (`Difficoltà`), exposure (`Esposizione...`) and the free texts. At most 15 detail pages per
  run, the newest first, each kept in the lookup cache (`report:<type>-<id>`); the others keep what the list gives
  (`detail_deferred` in `last_skipped`) until a next run. 2 s between requests, 17 at most (about 35 s a run). The
  ids are per type: the external id is `<type>-<id>`.
- **Activities.** From the type of the report: 1 Scialpinismo `skitouring` (the Blachère grade, MS/BS/OS and their
  `A` variants, gives the ski ratings, OS is steep), 2 Escursionismo `hiking`, 3 Roccia `rock_climbing`, 4 Ghiaccio
  e misto `mountain_climbing` (`ice_climbing` when the title names an ice fall: `cascata`, `ice fall`,
  `candela`), 6 MTB `mountain_biking`. Types 5 and 7 list nothing (`unmapped_activity:<type>` if they ever do).
  The other grades (`E`, `TD- / 6b`, `III / S2`) are kept in `rating_raw`.
- **Location.** No coordinates and no GPX anywhere on the site. An outing has the hints of
  [Outings without coordinates](#outings-without-coordinates): `summit_name` (the head of the title, before a comma
  or a dash, without its elevation), `elevation_max`, `region` (an Italian region, or `Svizzera`, `Francia`...)
  and `country` (`IT` for the Italian regions, `CH`, `FR`...; none for `Altro`). An unmatched summit falls back to
  the region table (below), then to the country.
- **Regions to areas.** c2c has no area for the Italian regions: its Italian `admin_limits` are the 110 provinces
  (2011 borders: 109 `Provincia di ...` and `Valle d'Aosta`). `partners/regions/onice.json` maps each of the 20
  Italian regions to the list of its provinces, the first (hand-picked: the province of its main mountains, Lombardia
  -> Sondrio, Piemonte -> Torino...) giving the `area_centroid` position; `Svizzera`, `Francia`... are country-only
  entries (no `area_ids`); `Altro` is in no table. The ids were read in the dev database on 2026-11-27, the file's
  `coverage` block says how.
- **Texts.** `Commento` (narrative), `Condizioni`, `Valutazione itinerario`, `Rischio valanghe` (conditions),
  `Neve prevalente`, `Altra neve` (snow), `Partenza`, `Rifugio di appoggio` (access), `Attrezzatura consigliata`
  (equipment) go to `texts`, redacted in a recording (`REDACT_SELECTORS`). The author row of a detail page is never
  read: the site keeps the author's e-mail in an HTML comment there (a test checks that no fixture holds an e-mail).
- **Quirks.** Plain `http` only (https fails). The pages are ISO-8859-1 with some UTF-8 bytes in fields (`30Â°`):
  the adapter decodes them itself (UTF-8, else Windows-1252, then the mojibake of a field) and a recording is written
  in UTF-8. The markup is loose (text after `</html>`): `html.parser` copes. An unknown id answers HTTP 200 with a PHP
  `Fatal error`: no `td.report-title`, the report is taken for gone (`detail_gone`, cached). The rows of a detail
  page depend on its type, so `REQUIRED_SELECTORS` reads them through one selector (any of the labels read), plus
  the rows every type has (grade, comment).
- **Terms.** No `robots.txt` (404), no licence statement, no RSS. We show title, date, author, region and the link,
  with the credit; ask the site before enabling it.



```
python -m c2corg_api.partners shapes <source> [--offline] [--fixtures DIR]
```

Runs the adapter live (nothing is written) and prints the differences between
the shapes of the answers and the `shape.json` of the fixtures, one line per
path: `+ path: type` added, `- path` removed, `~ path: old -> new` retyped.
Only what the adapter reads can make it fail: each adapter declares
`REQUIRED_PATHS` (every path it reads, also the allow-list of the recorder) (endpoint -> JSON paths, `[]` for list items, for example
`sorties: [].sommets[].latlon`). Fields the adapter does not read are ignored on both sides (the
same allow-list trims the live answers), so a new field of the site is not
reported: the adapter does not use it. A required path under an empty list of the sample is
listed as `unchecked`.

`--offline` replays the fixtures instead of calling the site: a self-check
that needs no network and no key.

| Exit code | Meaning |
|---|---|
| 0 | every field the adapter reads is still there |
| 1 | a required path is missing or retyped, or the adapter cannot parse the answer: the partner changed its API |
| 2 | the check could not run: site blocked (`401/403/429`, challenge page), down, secret missing, no `shape.json` |

### Live contract tests

```
PARTNER_LIVE=1 uv run pytest -m partner_live c2corg_api/tests/partners
```

`c2corg_api/tests/partners/test_live.py` runs each real adapter against its
real site (one run, within the adapter's request budget) and asserts that every
`REQUIRED_PATHS` entry exists with the type of the fixtures. They are not part
of `make test` or CI: the default options of pytest carry `-m "not
partner_live"` (the later `-m partner_live` replaces it), and without
`PARTNER_LIVE=1` they are skipped. A missing key (`SKITOUR_API_KEY`), a blocked
or unreachable site skips the test with the reason: that is availability, not a
contract change. Use `-rs` to see the reasons.

### What the sandbox reaches (2026-11-24)

| Source | From the dev sandbox | `record` / `shapes` / live test |
|---|---|---|
| skitour.fr | no key, so exit 2 / skip "disabled: SKITOUR_API_KEY not set"; unreachable from the dev container ("down") | needs `SKITOUR_API_KEY` |
| gulliver.it | Cloudflare challenge (403) from cloud addresses: "blocked", exit 2 / skip; reachable from a home connection with the camptocamp User-Agent (2026-11-27) | `record` makes up to 45 requests, 2 s apart (about 1.5 min) |
| bivouak.net | reachable | `record` makes up to 15 requests, 10 s apart |
| gipfelbuch.ch | reachable (robots.txt allows all) | `record` makes up to 17 requests, 2 s apart |
| skitourenportal.eu | reachable, without `www` (recorded 2026-11-25) | no key |
| on-ice.it | reachable over plain `http` (recorded 2026-11-27) | `record` makes up to 17 requests, 2 s apart |

Run them from a workstation or from production infrastructure; in the sandbox
they only report why they could not run.

## Production notes

- **Contact the partners first.** Both sites are reused for the benefit of their communities: tell skitour.fr and
  gulliver.it what we do, with the credit and link shown on every row, and get their agreement (and the API key
  for skitour.fr); switch a source off in production while its agreement is missing. The credit of each row is `credit` in the answer.
- **User agent.** The job identifies itself: `camptocamp.org partner-index (+https://www.camptocamp.org)`. Keep it,
  so that the partners can recognize, throttle or contact us.
- **Gulliver allowlisting.** `gulliver.it` is behind a Cloudflare JavaScript challenge: from datacenter addresses the
  source is `blocked` (403 with a challenge page); a home connection gets through with our User-Agent. Its terms
  ("Contributi e proprietà") allow reuse only with prior permission: ask before enabling it. Ask Gulliver to allowlist our egress address or user agent (or to
  give a token: it would be `GULLIVER_API_TOKEN`, read like `SKITOUR_API_KEY`). Never try to bypass the challenge.
- **Rate limits.** Each adapter declares its politeness (`rate` in `partners/sources/*.py`): a minimum delay between
  requests and a budget of requests per run (skitour: 1.1 s, 10 requests; gulliver: 2 s, 45 requests; bivouak: 10 s, 15 requests; gipfelbuch: 2 s, 18 requests; on-ice.it: 2 s, 17 requests). A spent budget
  makes the run `down`.
- **Enabling.** All the sources are on by default (`harvest_partners_enabled="true"`, `partners_transport="http"`).
  Switch one off with `harvest_partners_<name>_enabled="false"` (or all with `harvest_partners_enabled="false"`) while
  an agreement is missing, and put `SKITOUR_API_KEY` in the environment of the background-jobs container: without it
  skitour stays `disabled`.
- **Monitoring.** `/health` lists each source under `harvest` (`partners.skitour: {sources, failing, last_success}`)
  without ever failing the check; look at
  `/partner-outings/sources` (`status_detail`, `last_success_at`, `last_skipped`) when a source is not `ok`.
- **Fixtures.** Every source has a real recording now (`manifest.json` says `synthetic: false`); the edge cases a
  recording lacks are in separate synthetic directories (`skitour_synthetic`, `gulliver_synthetic`), used by the
  adapter tests only.

## gipfelbuch.ch

The "Verhältnisse" (conditions reports) of Switzerland, Austria, Germany, Italy and France: one listing page
(`/verhaeltnisse/uebersicht`, about 66 reports of every activity, newest first; the old `/gipfelbuch/verhaeltnisse`
URL redirects there, and the `src_conditions_type` filter is not a GET parameter, so every activity comes back).

- **Activities.** Read from the label of the activity icon (`Skitour`, `Wanderung`, ...). Mapped: skitour and
  freeride to `skitouring`, schneeschuhtour to `snowshoeing`, wanderung to `hiking`, klettertour to `rock_climbing`,
  eisklettern to `ice_climbing`, klettersteig to `via_ferrata`, hochtour to `mountain_climbing`, bike to
  `mountain_biking`. Canyoning, "Anderer Routentyp" and reports without a route type are counted in
  `last_skipped` as `unmapped_activity:<code>`.
- **Location.** The listing has no coordinates: only the summit name and altitude (`Regenflüeli (1582m)`), the region
  (`CH - Zentralschweiz`) and the country. The adapter gives them as `summit_name`, `elevation_max`, `region` and
  `country` (`CH`, `AT`, `DE`, `IT`, `FR`, `LI`). The page of a report holds a map element with WGS 84 `data-lat` /
  `data-lon` (the point of the route's summit, entered by the contributors). It is read once per summit and kept in
  `partner_lookups` (`summit:<name>_<altitude>`), at most 15 new summits per run (`summit_lookup_deferred` in `last_skipped`
  counts the rest, which come on the next runs; `lookup_failed` the pages that answered 5xx or did not answer); such
  outings get `geom_quality = 'summit'`. The others keep the hints for the job's resolver
  ([Outings without coordinates](#outings-without-coordinates)): `summit_match`, else their country.
- **Parsing.** By labelled element (`REQUIRED_SELECTORS`, via `htmlparse`), never by position.

## gulliver.it

The trip reports ("gite") of the WordPress API of the site (`/wp-json/gulliver/`), every activity, recorded live on
2026-11-27 (`sources/gulliver.py` has the details of the format).

- **Discovery.** `mobile/commentglobal?page=1..5`: 30 reports a page, an object keyed by report id, sorted by the date
  of the OUTING (a day) with many ties: the pages overlap (37 duplicates in 150) and skip reports (about a quarter of
  the reports of the last days never show up). So the adapter also reads `front_page/comments?sorting=id`, the HTML
  fragment of the home page with the 50 most recently posted reports (the site's own script asks for it): the reports
  it lists that the pages did not hold, dated from `since - 7 days` (late posts about older outings), are read with
  `mobile/comments?id=` (at most 15 a run). Paging stops at the first page that reaches back before `since`. No cursor:
  every report read is kept in `partner_lookups` (`report:<id>`), so a report is asked for once.
- **Routes.** `mobile/routes?id=` (heavy: about 600 KB with the media) gives the title, region, start point
  (`geom_quality = 'start'`), top altitude, height difference, exposure and grade. At most 24 new routes a run, those of
  the ski reports first; each kept in `partner_lookups` (`route:<id>`, the extracted fields only; an unknown id, which
  answers an empty skeleton, as `{"empty": true}`). A report whose route is not known yet keeps the title of the route
  summary of `comments?id=` or of its link, and is completed by a later run.
- **Budget.** 5 pages + 1 front page + 15 reports + 24 routes = 45 requests, 2 s apart, at most (about 1.5 min); a
  run in the steady state makes a handful (the lookups are cached).
- **Activities** (`term.code`): `skimo` and `skisteep` (steep: `true`) to `skitouring`, `snowshoe` to `snowshoeing`,
  `hike` to `hiking`, `climb` and `crag` to `rock_climbing`, `mountain` to `mountain_climbing`, `iceclimb` to
  `ice_climbing`, `ferrata` to `via_ferrata`, `mtb` to `mountain_biking`. `cycle` (road cycling) and `skinord` (Nordic
  skiing) have no c2c activity: `unmapped_activity:<code>` in `last_skipped`.
- **Grades.** `grade_skimo` is a Blachère grade (`MS`, `BS`, `OS`, `A` suffix: `rating_system = 'blachere'`, `OS` is
  steep); `grade_skisteep` a c2c-like ski rating (`4.1`: `c2c_ski`, steep from 4.1). The exposure is Italian
  (`Nord-Est`...; `Varie`, `Tutte`: none). The snow line (`snow_alt`) is `snow.line_m`; the snow qualities
  (`Polverosa`...) are texts (`texts.snow`).
- **Region and country.** `<region> - <district>` (`Valle d'Aosta - AO`); the country is `FR` for a region ending
  with `(FR)` (and so on), else `IT`. For Italy the district is the province code: `partners/regions/gulliver.json`
  holds the 20 regions (as on-ice.it's table) and the 110 province codes (plus `SU`, Sud Sardegna, as the old
  provinces it covers), so a report without route coordinates gets the centroid of its province (`area_centroid`),
  or of its region when the code is unknown. Foreign regions are not in it (the country only). A report whose route
  was not looked up yet has no region at all.
- **GPX.** The first track of a report (`tracks[0].guid`) is `gpx_url` when it is an `https` link to a `.gpx` file on
  gulliver.it. The files are public, but hold personal data (times, heart rate) and fall under the terms of the site.

## GPX tracks

The points of the GPX file of a partner outing (`gpx_url`), stored in `guidebook.partner_tracks` and served as a
GeoJSON Feature. Only the sources whose adapter declares a licence for their tracks (`TRACK_LICENCE`) have them:
gulliver.it, `CC BY-NC-ND` (shown as-is, with the author and the site as credit).

- **A second phase of a run** (`jobs/partner_tracks.py`): after the outings of a source are stored, at most
  `partners.tracks_per_run` files (3) are read, **newest outings first** (date, then id, descending), one every
  `partners.tracks_interval_seconds` (10 s at least), with a transport and a request budget of their own: the JSON
  harvest never waits for them, and a failing file never changes the status of the source. Its counts are in the
  harvest summary of the run (`tracks: {ok, failed, invalid}`).
- **Failures.** A file the site fails to serve (5xx, timeout) is `failed`, and tried again after 1, 2, 4 hours, 4 times
  at most. A file that is not a usable GPX (404, not XML, too big, no line, a DTD or entities) is `invalid`, and read
  again only when the outing links to another file. A block (403, challenge) stops the phase for the run.
- **Personal data.** The GPX files of the users hold times, heart rates, device and author names. The reader
  (`partners/gpx.py`, defusedxml: no DTD, no entity, no external reference; at most 5 MB, read in a stream and cut
  beyond; at most 200 000 points) keeps the longitude and latitude of the points of the tracks and routes only; the
  waypoints, the times, the extensions and the metadata are never stored. Elevations are not stored (2D, as the c2c
  geometries).
- **Size.** A track of more than 2000 points is simplified (Douglas-Peucker, the tolerance doubled from 2 m until it
  fits; `simplified: true`). This reduces the display size only: the licence allows no derivative work, so the
  original file stays linked (`gpx_url`) and credited.
- **Storage.** `partner_tracks` (one row per outing, `source` + `external_id`, deleted with its outing): `geom`
  (MULTILINESTRING, EPSG:3857), `point_count` (the points of the file), `simplified`, `gpx_url` (the file read),
  `status` (`ok`, `failed`, `invalid`), `detail`, `attempts`, `last_attempt_at`, `fetched_at`.
- **API.** The items of `GET /partner-outings` have `has_track` (a stored track); `GET /partner-outings/{id}/track`
  (`id` as in the listing, `gulliver:350592`) answers the Feature, `Cache-Control: public, max-age=3600`, or 404:

  ```json
  {"type": "Feature", "id": "gulliver:350592",
   "geometry": {"type": "MultiLineString", "coordinates": [[[8.325, 46.155], ...]]},
   "properties": {"source": "gulliver", "url": "https://www.gulliver.it/itinerari/.../350592/",
                  "gpx_url": "https://www.gulliver.it/wp-content/uploads/2026/11/AnelloBorgateMontecrestese.gpx",
                  "author": "user12", "attribution": "© user12 / gulliver.it — CC BY-NC-ND",
                  "licence": "CC BY-NC-ND", "point_count": 60, "simplified": false}}
  ```

- **Fixtures.** `fixtures/gulliver_tracks/` (`synthetic: true`) holds made-up GPX files at the links of the three newest
  reports with a GPX of the gulliver recording, so the demo shows tracks (with `partners_allow_synthetic="true"`, as
  in `env.dev`); real files of the users are never committed. Without that directory, or with synthetic fixtures not
  allowed, fixture mode has no track phase.
- **Backfill.** Nothing more is needed to read the tracks of older outings: each run takes the newest outings
  without a track, so the older ones come as the budget allows (or with a bigger `partners.tracks_per_run` for a
  while). The backfill of the outings themselves is [c2corg/v6_api#2763](https://github.com/c2corg/v6_api/issues/2763).
