# Partner outings

The `/metaskirando` view of the UI shows, next to the outings of Camptocamp, the outings reported on partner
sites ([skitour.fr](https://skitour.fr), [gulliver.it](https://www.gulliver.it)). The API does not proxy the
partner sites at request time: a job harvests them every 15 minutes into its own tables, and
`GET /partner-outings` merges those rows with the c2c outings of the same period.

```
partner site -> adapter (c2corg_api/partners/sources/<name>.py, pure) -> job (jobs/harvest_partner_outings.py)
             -> guidebook.partner_outings / partner_sources / partner_lookups
             -> GET /partner-outings, GET /partner-outings/sources, GET /health  (views/partner_outings.py)
```

- An adapter only turns the answers of the site into `HarvestedOuting` objects. It gets its HTTP transport and its
  lookup cache from the job, so it runs unchanged on recorded fixtures.
- The job stores the rows (one per source and external id), assigns the c2c areas that contain the point of each
  outing, records the health of each source, and a second job purges the outings older than the retention.
- The design is in `doc/meta/A2_HARVESTER.md` of c2corg/metaskirando-archive.

## Configuration

Non-secret settings: `config/env.default`, overridden for the dev stack in `config/env.dev`, rendered in
`common.ini` (`make load-env`).

| env key | ini key | default | meaning |
| --- | --- | --- | --- |
| `partners_enabled` | `partners.enabled` | `false` (`true` in `env.dev`) | the scheduler harvests (`make harvest-partners` also needs it) |
| `partners_sources` | `partners.sources` | `skitour,gulliver` | adapters to run |
| `partners_interval` | `partners.interval_minutes` | `15` | scheduler period; base of the backoff |
| `partners_retention` | `partners.retention_days` | `31` | outings older than that are not stored, and purged |
| `partners_transport` | `partners.transport` | `http` (`fixtures` in `env.dev`) | `http`: the real sites; `fixtures`: recorded answers, no network |
| `partners_fixtures_dir` | `partners.fixtures_dir` | empty | empty: `c2corg_api/tests/partners/fixtures` |

Secrets come from the environment only (`.env` locally, Docker secrets in production), never from the ini files:

- `SKITOUR_API_KEY`: the key of the skitour.fr API. Without it the source is `disabled`. Ask skitour.fr for a key; do
  not reuse any key found in old code.
- Gulliver needs none today.
- In fixture mode no secret is needed.

## Statuses of a source

`GET /partner-outings/sources` (and `partners` in `GET /health`) tell the state of each source after its last run.

| status | meaning | counts as a failure |
| --- | --- | --- |
| `never_run` | no run yet (a source of `partners.sources` without a row) | no |
| `ok` | the run went through, nothing skipped for an error | no |
| `degraded` | the run stored its outings, but some items could not be parsed (below the failure threshold) | no |
| `failing` | a bug, too many unparsable items (more than 3 and 10%), or a storage error: nothing stored | yes |
| `blocked` | the site refuses us: 401/403/429 or an anti-bot challenge page (Cloudflare) | yes |
| `down` | the site does not answer: 5xx, timeout, or the request budget of the run is spent | yes |
| `disabled` | the source cannot run by choice: a secret is missing (`status_detail` says which) | no |

After 3 failed runs in a row (`failing`, `blocked`, `down`) the job waits 2 x, 4 x, ... the interval (at most 16 x)
before trying again. `blocked` is not `down`: a blocked source needs an agreement or an allowlisting from the
partner, retrying more often only makes it worse. `status_detail` never contains a secret.

A source that fails never stops the other sources, and its previous outings stay listed until the retention purge.

## Local demo

Fixture mode runs the real job and the real adapters on recorded (here: synthetic) answers of the partner sites,
so the whole chain works offline. The fixtures hold 10 skitour.fr and 9 gulliver.it outings with coordinates in the
Alps (Vanoise, Belledonne, Vercors, Aosta valley...), some without coordinates, one old one, and a few items that do
not parse on purpose: both sources end `degraded`, which is the expected demo status. When the job runs, the dates
are shifted so that the newest fixture outings are dated today.

With the dev stack of the README (`scripts/sandbox-up.sh`, or the dev container, with the anonymized dev
database): `config/env.dev` already has `partners_enabled="true"` and `partners_transport="fixtures"`.

```bash
# in the app container (docker compose ... exec app bash), from the repository
make CONFIG=config/env.devcontainer load-env   # only if the ini files predate the partners settings
uv run alembic upgrade head                    # creates the partner tables (setup.sh already does it)
make harvest-partners                          # runs the job once: skitour.fr and gulliver.it fixtures
make serve                                     # API on :6543 (already running after sandbox-up.sh)
```

`make harvest-partners` logs a lot of SQL; the last lines tell the status of each source
(`Partner source skitour: degraded (10 upserted)`). Then:

```bash
curl -s 'localhost:6543/partner-outings' | python3 -m json.tool | head -60
curl -s 'localhost:6543/partner-outings?act=skitouring'
curl -s 'localhost:6543/partner-outings?steep=true'                 # ski rating 4.1+ (or global D-+)
curl -s 'localhost:6543/partner-outings?sources=gulliver'
curl -s 'localhost:6543/partner-outings?a=14409'                    # the Vanoise range of the demo database
curl -s 'localhost:6543/partner-outings?date=2026-06-18,2026-07-18&sources=c2c'   # the c2c outings of the demo database
curl -s 'localhost:6543/partner-outings/sources' | python3 -m json.tool
curl -s 'localhost:6543/health'                                      # "partners": {"skitour": "degraded", ...}
```

Notes:

- The answer is `{total, items, sources}`. The default window is the last 14 days. The anonymized database
  has no recent c2c outings (the newest are months old), so the default window shows partner rows only: ask for an
  old window with `date=<from>,<to>` (31 days at most) to see c2c rows, and `sources=c2c` or `sources=skitour,gulliver`
  to select a side.
- The fixture coordinates fall in real areas of the demo database: the `areas` of each item are filled
  (country, department, range). Rows without a point (or outside any area) have `areas: []`.
- Run the job again whenever you like: it is idempotent (upsert), and shifts the dates to the current day.
  `make run-background-jobs` starts the scheduler, which re-harvests every `partners.interval_minutes`.
- The answers are cached for 2 minutes (Redis): after a new harvest, wait or flush with `make flush-redis`.
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

`<source>` is `skitour` or `gulliver`. The command runs the real adapter with
the real transport, through a `RecordingTransport`, and writes into
`<out>/<source>/` (default: the tests fixtures directory):

- the response files and `manifest.json` (`synthetic: false`, `recorded_at`
  today). The number of days asked from skitour (`j`) is not recorded, so the
  fixtures fit any `since`;
- `shape.json`: the shape (keys and value types) of every recorded JSON file,
  keyed by file name. `shapes` compares with it.

Payloads are trimmed before they are written: lists are cut to 30 items, and
fields the adapters never read are dropped. Those are the skitour texts and
photos (`conditions`, `recit`, `photos`: their licence forbids reusing them),
the gulliver comment texts and the route media. Secrets come from the
environment (`SKITOUR_API_KEY`) and are never written.

The recording is made aside and installed only when it succeeded: a blocked or
down site leaves the existing fixtures untouched. Review `git diff`, run the
tests, and commit. The synthetic fixtures of M1 are replaced this way, from a
machine the sites do not block.

### Checking for changes: `shapes`

```
python -m c2corg_api.partners shapes <source> [--offline] [--fixtures DIR]
```

Runs the adapter live (nothing is written) and prints the differences between
the shapes of the answers and the `shape.json` of the fixtures, one line per
path: `+ path: type` added, `- path` removed, `~ path: old -> new` retyped.
Only what the adapter reads can make it fail: each adapter declares
`REQUIRED_PATHS` (endpoint -> JSON paths, `[]` for list items, for example
`sorties: [].sommets[].latlon`). Added fields and changes to other fields are
reported, not fatal. A required path under an empty list of the sample is
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
  requests and a budget of requests per run (skitour: 1.1 s, 10 requests; gulliver: 2 s, 40 requests). A spent budget
  makes the run `down`.
- **Enabling.** Keep `partners_enabled="false"` and `partners_transport="http"` (the defaults) until the agreements are
  there; then set `partners_enabled="true"` and the secret in the environment of the background-jobs container.
- **Monitoring.** `/health` lists `partners: {source: status}` without ever failing the check; look at
  `/partner-outings/sources` (`status_detail`, `last_success_at`, `last_skipped`) when a source is not `ok`.
- **Fixtures.** The recorded fixtures are synthetic (`manifest.json` says `synthetic: true`): the partner sites are not
  reachable from the sandboxes. Replace them with real recordings when the agreements allow it, and keep the
  adapters tested against them (`c2corg_api/tests/partners`).
