# Partner outings

The `/metaskirando` view of the UI shows, next to the outings of Camptocamp, the outings reported on partner
sites ([skitour.fr](https://skitour.fr), [gulliver.it](https://www.gulliver.it), [bivouak.net](https://www.bivouak.net)
and [gipfelbuch.ch](https://www.gipfelbuch.ch), the last two off by default). The API does not proxy the partner sites
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
- The job stores the rows (one per source and external id), assigns the c2c areas that contain the point of each
  outing, records the health of each source, and a second job purges the outings and the lookups older than the retention.
  That purge job is scheduled even when the harvest is off (`harvest_partners_enabled="false"`): the rows must not
  outlive the retention.
- The design is in `doc/meta/A2_HARVESTER.md` of c2corg/metaskirando-archive.

## Configuration

Non-secret settings: `config/env.default`, overridden for the dev stack in `config/env.dev`, rendered in
`common.ini` (`make load-env`).

| env key | ini key | default | meaning |
| --- | --- | --- | --- |
| `harvest_partners_enabled` | `harvest.partners.enabled` | `false` (`true` in `env.dev`) | the scheduler harvests the partner sources, whatever `harvest.enabled`; `make harvest-partners` refuses to run unless a source is on or `--force` is given |
| `harvest_partners_<name>_enabled` | `harvest.partners.<name>.enabled` | empty (`false` for `bivouak` and `gipfelbuch`, `true` in `env.dev`) | one source: `true`/`false`, empty as `harvest.partners.enabled` (absent is empty). A new source is `false` in `env.default` until the site agrees |
| `partners_interval` | `partners.interval_minutes` | `15` | minutes between two runs of a source (its harvest policy); base of the backoff |
| `partners_retention` | `partners.retention_days` | `31` | outings older than that are not stored, and purged |
| `partners_lookup_retention` | `partners.lookup_retention_days` | `30` | `partner_lookups` rows (cached route lookups) older than that are purged |
| `partners_transport` | `partners.transport` | `http` (`fixtures` in `env.dev`) | `http`: the real sites; `fixtures`: recorded answers, no network |
| `partners_fixtures_dir` | `partners.fixtures_dir` | empty | empty: `c2corg_api/tests/partners/fixtures` |
| `partners_allow_synthetic` | `partners.allow_synthetic` | `false` (`true` in `env.dev` only) | fixture mode may run on a manifest with `synthetic: true`. Otherwise the source is `failing` (ERROR log, detail says why) and nothing is stored: hand-made data can never be published by accident |

Secrets come from the environment only, never from the ini files. Each secret `NAME` is read from `$NAME`; when that
is not set, from the file named by `$NAME_FILE` (the Docker secrets convention, e.g.
`SKITOUR_API_KEY_FILE=/run/secrets/skitour_api_key`; the content is stripped of surrounding whitespace). `$NAME` wins
when both are set.

- `SKITOUR_API_KEY` or `SKITOUR_API_KEY_FILE`: the key of the skitour.fr API. Without it the source is `disabled`. Ask skitour.fr for a key; do
  not reuse any key found in old code.
- Gulliver needs none today.
- In fixture mode no secret is needed.

## Statuses of a source

`GET /partner-outings/sources` (and `partners` in `GET /health`) tell the state of each source after its last run.

| status | meaning | counts as a failure |
| --- | --- | --- |
| `never_run` | no row yet: the job has not run since the source exists (`/partner-outings/sources` lists every known source, with or without a row) | no |
| `ok` | the run went through, nothing skipped for an error | no |
| `degraded` | the run stored its outings, but some items could not be parsed (below the failure threshold) | no |
| `failing` | a bug, too many unparsable items (more than 3 and 10%), or a storage error: nothing stored | yes |
| `blocked` | the site refuses us: 401/403/429 or an anti-bot challenge page (Cloudflare) | yes |
| `down` | the site does not answer: 5xx, timeout, or the request budget of the run is spent | yes |
| `disabled` | the source does not run by choice: a secret is missing, or it is switched off (`status_detail` says which: `not configured`, set when the scheduler starts) | no |

A failed run (`failing`, `blocked`, `down`) is an error of its harvest source (`PartnerRunFailed`, in
`harvest_sources.last_error`): the harvest policy waits 1 x, 2 x, 4 x... the interval (at most 16 x) before trying
again. `blocked` is not `down`: a blocked source needs an agreement or an allowlisting from the
partner, retrying more often only makes it worse. `status_detail` never contains a secret.

A source that fails never stops the other sources, and its previous outings stay listed until the retention purge.

## Local demo

Fixture mode runs the real job and the real adapters on recorded (here: synthetic) answers of the partner sites,
so the whole chain works offline. The fixtures hold 10 skitour.fr and 9 gulliver.it outings with coordinates in the
Alps (Vanoise, Belledonne, Vercors, Aosta valley...), some without coordinates, one old one, and a few items that do
not parse on purpose: both sources end `degraded`, which is the expected demo status. When the job runs, the dates
are shifted so that the newest fixture outings are dated today.

With the dev stack of the README (`scripts/sandbox-up.sh`, or the dev container, with the anonymized dev
database): `config/env.dev` already has `harvest_partners_enabled="true"`, `partners_transport="fixtures"` and
`partners_allow_synthetic="true"` (the demo fixtures are synthetic; without it the sources end `failing`).

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

`<source>` is `skitour`, `gulliver`, `bivouak` or `gipfelbuch`. The command runs the real adapter with
the real transport, through a `RecordingTransport`, and writes into
`<out>/<source>/` (default: the tests fixtures directory):

- the response files and `manifest.json` (`synthetic: false`, `recorded_at`
  today). The number of days asked from skitour (`j`) is not recorded, so the
  fixtures fit any `since`;
- `shape.json`: the shape (keys and value types) of every recorded JSON file,
  keyed by file name. `shapes` compares with it.

Payloads are trimmed before they are written, by an **allow-list**: only the
paths an adapter lists in its `REQUIRED_PATHS` are kept, everything else is
dropped, and lists are cut to 30 items. No partner free text (skitour
`conditions`, `recit`, `photos`; gulliver `content`, `meta.access`, `meta.obs`,
`tracks`...) reaches a fixture, whatever new fields the site adds: their licence
forbids reusing it. A test scans the committed fixtures for such keys. Secrets come from the
environment (`SKITOUR_API_KEY`) and are never written.

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

### Checking for changes: `shapes`

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
| gulliver.it | Cloudflare challenge (403): "blocked", exit 2 / skip | needs an allowed network or a Gulliver allow-list |
| bivouak.net | reachable | `record` makes up to 15 requests, 10 s apart |
| gipfelbuch.ch | reachable (robots.txt allows all) | `record` makes up to 17 requests, 2 s apart |

Run them from a workstation or from production infrastructure; in the sandbox
they only report why they could not run.

## Production notes

- **Contact the partners first.** Both sites are reused for the benefit of their communities: tell skitour.fr and
  gulliver.it what we do, with the credit and link shown on every row, and get their agreement (and the API key
  for skitour.fr) before enabling the source in production. The credit of each row is `credit` in the answer.
- **User agent.** The job identifies itself: `camptocamp.org partner-index (+https://www.camptocamp.org)`. Keep it,
  so that the partners can recognize, throttle or contact us.
- **Gulliver allowlisting.** `gulliver.it` is behind a Cloudflare JavaScript challenge: from datacenter addresses the
  source is `blocked` (403 with a challenge page). Ask Gulliver to allowlist our egress address or user agent (or to
  give a token: it would be `GULLIVER_API_TOKEN`, read like `SKITOUR_API_KEY`). Never try to bypass the challenge.
- **Rate limits.** Each adapter declares its politeness (`rate` in `partners/sources/*.py`): a minimum delay between
  requests and a budget of requests per run (skitour: 1.1 s, 10 requests; gulliver: 2 s, 40 requests; bivouak: 10 s, 15 requests; gipfelbuch: 2 s, 18 requests). A spent budget
  makes the run `down`.
- **Enabling.** Keep `harvest_partners_enabled="false"` and `partners_transport="http"` (the defaults) until the
  agreements are there; then set `harvest_partners_enabled="true"` (or one source with
  `harvest_partners_<name>_enabled="true"`) and the secret in the environment of the background-jobs container.
- **Monitoring.** `/health` lists each source under `harvest` (`partners.skitour: {sources, failing, last_success}`)
  without ever failing the check; look at
  `/partner-outings/sources` (`status_detail`, `last_success_at`, `last_skipped`) when a source is not `ok`.
- **Fixtures.** The recorded fixtures are synthetic (`manifest.json` says `synthetic: true`): the partner sites are not
  reachable from the sandboxes. Replace them with real recordings when the agreements allow it, and keep the
  adapters tested against them (`c2corg_api/tests/partners`).

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
  counts the rest, which come on the next runs); such outings get `geom_quality = 'summit'`. The others keep the
  hints for the job's resolver.
- **Parsing.** By labelled element (`REQUIRED_SELECTORS`, via `htmlparse`), never by position.
