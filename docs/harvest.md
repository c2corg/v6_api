# Harvesting (avalanche bulletins)

The scheduler (`make run-background-jobs`, `c2corg_api/scripts/jobs/scheduler.py`) fetches data from outside services
in the background and stores it in PostgreSQL, so that the API reads it from the database instead of asking the
services at each request. The first data harvested are the avalanche bulletins: the BRA of Météo-France (one per French
massif) and the CAAML v6 files of the EAWS services of the Alps and the Pyrenees (SLF, avalanche.report,
lawinen-warnung.eu, AINEVA, Lauegi...).

The code is in two parts:

- `c2corg_api/harvest/`: the generic part. `harvester.py` (what a harvester is), `policy.py` (when to fetch a source
  again), `runner.py` (the tick, the claims, the errors, the health status).
- `c2corg_api/avalanche_bulletins/`: the avalanche harvesters (`harvesters.py`), the requests and parsing shared with
  the on-demand fetch (`meteofrance.py`, `caaml.py`), the storage (`store.py`, `weather.py`) and the read path
  (`regions.py`, `cache.py`, routes in `c2corg_api/web/avalanche_bulletins.py`).

The tables are created by the migration `5e3c1a7b9d42` (`alembic_migration/versions/`). See the
[backend diagram](https://c2corg.github.io/v6_api/architecture/backend.html).

## Scheduling

A **harvester** has **sources** (`avalanche.meteofrance:FR-03`, `avalanche.caaml:CH:fr`): one URL each, fetched and
stored on its own. Each source is a row of `harvest_sources`, whose `next_run_at` says when it is due.

The scheduler runs `harvest_tick` **every minute** (APScheduler, `max_instances=1`, `coalesce`: a tick still running
makes the next one wait). A tick:

1. every 10 minutes, **syncs** the sources: the sources a harvester lists and the table lacks are added (due now);
   those it no longer lists are disabled (`disabled_at`); a disabled source listed again comes back with its state.
2. **claims** the due sources (`next_run_at <= now`, not disabled, oldest first), with `SELECT ... FOR UPDATE SKIP
   LOCKED`: a source claimed by another scheduler is left to it. Claiming moves `next_run_at` 10 minutes later (the
   lease): a run that dies (crash, restart) is retried after it. At most 60 sources a tick, and at most
   `requests_per_minute` for a harvester with a quota.
3. fetches them in 4 threads, in **lanes by host**: at most 2 lanes for a host, each lane run in turn by a worker, so a
   service never gets more than 2 requests at once, and a slow service does not hold the others.
4. for each source, sends a **conditional GET** (`If-None-Match`, `If-Modified-Since`). A 304, or a content with the
   same SHA-256 as last time, stores nothing. A new content is kept as a payload, then stored by the harvester.
5. records the result and the next `next_run_at`, computed by `policy.next_run`.

```mermaid
flowchart TD
    tick([harvest_tick, every minute]) --> sync{10 min since<br/>the last sync?}
    sync -- yes --> syncsrc[sync_sources: add new,<br/>disable gone, re-enable back]
    sync -- no --> claim
    syncsrc --> claim[claim the due sources<br/>FOR UPDATE SKIP LOCKED<br/>next_run_at = now + lease]
    claim --> lanes[lanes by host, 2 per host,<br/>4 worker threads]
    lanes --> fetch[fetch: conditional GET]
    fetch -- 304 --> ok
    fetch -- error --> err[error_count + 1, last_error<br/>next_run_at with backoff]
    fetch -- content --> same{same SHA-256<br/>as last time?}
    same -- yes --> ok
    same -- no --> keep[keep the payload<br/>harvest_payloads, gzipped]
    keep --> store[harvester.store<br/>bulletins, danger, weather]
    store -- error --> err
    store --> ok[last_success, error_count = 0<br/>next_run_at = policy.next_run]
```

### The policy

Each harvester has a `Policy` (`harvest/policy.py`); the avalanche harvesters share `AVALANCHE_POLICY`:

- **Season**: from November 1st to June 30th. Out of season, one check a day, at the start of the first window.
- **Windows**: the times the services publish, Paris time: 07:00-10:00 and 15:30-19:00, a fetch every 15 minutes.
  Outside the windows, every 60 minutes (`default_every`), and never past the start of the next window.
- **After a publication**: once a window saw a new publication (`last_publication`), an update is still possible but
  rarer: every 60 minutes until the window ends (`after_publication_every`).
- **Backoff**: after errors, 15 minutes, doubled at each error up to 4 hours. An error never brings the next fetch
  closer than the schedule would.
- **Jitter**: up to 60 seconds added, to spread the fetches.

`requests_per_minute` bounds the sources a tick claims for a harvester: 40 for Météo-France, whose key allows 50
requests a minute, shared with the PDFs the API fetches on demand. The CAAML services have no quota.

### Switching it on

- `harvest.enabled` (`.ini`, from `harvest_enabled` in `config/env.default`, `false` by default) switches on all the
  harvesters; `harvest.<name>.enabled` (`harvest.avalanche.meteofrance.enabled`, `harvest.avalanche.caaml.enabled`)
  overrides it for one harvester.
- With no harvester switched on, the scheduler registers none of the harvest jobs (tick, pruning, compaction).
- Without `METEOFRANCE_API_KEY`, the Météo-France harvester lists no source: its sources get disabled.

## State and health

`harvest_sources`, one row by source:

| Column | |
| --- | --- |
| `id`, `harvester` | `avalanche.caaml:CH:fr`, `avalanche.caaml` |
| `next_run_at` | when it is due (indexed) |
| `last_attempt`, `last_success` | the last claim, the last fetch that went through |
| `last_change`, `last_publication` | the last new content, the last one holding a new publication |
| `error_count`, `last_error` | the errors in a row (0 after a success), the last one (1000 characters) |
| `etag`, `last_modified`, `content_sha256` | for the conditional GET, and to skip a content seen last time |
| `state` | JSONB a harvester keeps between two fetches (`Stored.state`) |
| `disabled_at` | no longer listed by its harvester: not fetched |

A disabled source is deleted 30 days later, with its payloads; its bulletins stay (`source_id` set to null).

`GET /health` has a `harvest` section: by harvester, its enabled `sources`, those `failing` (`error_count > 0`) and the
latest `last_success`. A failing source does not fail the health check (the last data is still read); `harvest` is
`null` if the query fails, `{}` while nothing is harvested.

## Raw payloads

Each new content of a source is kept gzipped in `harvest_payloads`, for debugging and to parse the history again: only
when it changed, once per content (a content seen again moves its `fetched_at`). `prune_harvest`, at 02:00, deletes the
payloads older than `Harvester.keep_payloads_days` (30 days; 0 keeps none).

## Avalanche storage

- **`avalanche_bulletins`**: the bulletins as published (CAAML v6 JSON, normalized as on demand), one row by
  publication and language (`provider`, `bulletin_id`, `lang`, `publication_time`). A publication changed by its service
  without a new time is updated in place. `main_date` is the day the bulletin is valid for; `region_keys` holds its
  regions and all the regions holding them (`AT-07-14-01`: `AT-07-14`, `AT-07`, `AT`), GIN-indexed, to find the
  bulletins of a region at any level.
- **`avalanche_bulletin_regions`**: the danger of each region on each day, from its latest publication of the day: the
  maximum rating (1-5), the ratings below and above the elevation bound, all the bands, the problems and the aspects.
  A few hundred rows a day, **kept forever** for the history of the danger.
- **Superseded publications**: a publication whose regions are all in a later publication of the same provider,
  language and day is deleted after **7 days** (`prune_harvest`, 02:00).
- **Compaction**: the 1st of each month at 03:00, `compact_avalanche_bulletins` removes the `customData` (all levels,
  all services) of the bulletins whose day is more than **18 months** old, and sets `compacted_at`. The texts, ratings,
  problems, regions and times stay.
- **SLF weather**: SLF sends the weather of each micro-region (`customData.CH.weather`: 13 of the 17 kB of a
  bulletin), the same in every language. It is stored once, apart, and not answered with the bulletins:
  `region_weather_hours` (temperature and snowfall limit by hour) and `region_weather_periods` (wind and new snow by
  day), the latest publication winning, a forecast hour becoming an observed one.

## Read path and caching

| Route | Reads |
| --- | --- |
| `GET /avalanche-bulletins/regions/{region_id}/latest` | the stored bulletins of the latest day (at most 3 days ago, not stale), else on demand |
| `GET /avalanche-bulletins/regions/{region_id}/latest/pdf` | the PDF of Météo-France, always on demand |
| `GET /avalanche-bulletins/regions/{region_id}/{date}` | the stored bulletins of a day (`YYYY-MM-DD`), 404 without |
| `GET /avalanche-bulletins/regions/{region_id}/ratings?from&to` | the danger by day from `avalanche_bulletin_regions` (7 days by default, a year at most) |

- **Stored bulletins** go through Redis (`cache_avalanche_bulletin`) under a key holding a version of the region and
  day (last publication time, row count, last id): a new publication changes the key at once. Kept 10 minutes for a
  day not over, without expiry for a day over (answered with `Cache-Control: immutable`, a week).
- **On demand**: a region with nothing stored (not harvested yet, harvest off) or a database error falls back to the
  services, as before the harvester, cached in Redis 10 minutes around the publications and an hour otherwise; the last
  copy is answered while the service fails.
- The language asked, else English, else the one published, by provider. `ratings` reads PostgreSQL directly.

## Adding a harvester

1. Subclass `Harvester` (`c2corg_api/harvest/harvester.py`) with a `name`, a `policy`, `sources()`, `url()`,
   `fetch()` and `store()`; set `requests_per_minute` if the service has a quota and `keep_payloads_days`.
2. `store()` writes with the session it is given, never `DBSession`: the runner commits it with the state of the source,
   or rolls both back. Return `Stored(published=True)` when there was a new publication (it slows the polling down).
3. Add it to `runner.harvesters()`.
4. Add its tables to `c2corg_api/models/` (imported by `models/__init__.py`) and an alembic migration.
5. Switch it on with `harvest.<name>.enabled` in the `.ini` files (`common.ini.in`, `config/env.default`).
6. Test it with a fake service (see `c2corg_api/tests/harvest/`), and add its pruning to a job if its data grows.

```python
import requests

from c2corg_api.harvest.harvester import Harvester, Payload, Stored
from c2corg_api.harvest.policy import Policy

class SnowHeightHarvester(Harvester):
    name = 'snow.stations'
    policy = Policy(default_every=60)
    keep_payloads_days = 7

    def sources(self):
        return ['north', 'south']

    def url(self, source):
        return f'https://example.org/stations/{source}.json'

    def fetch(self, source, state):
        response = requests.get(
            self.url(source), headers=state.conditional_headers(), timeout=(3, 10)
        )
        return Payload.of(response)  # raises NotModified on 304

    def store(self, session, source, payload):
        rows = parse(payload.content)
        new = save_rows(session, rows)  # with `session` only
        return Stored(published=new)
```

## Operations

- `METEOFRANCE_API_KEY` (environment variable): the key of the Météo-France DPBRA API, 50 requests a minute, shared by
  the harvester (40 a tick at most) and the on-demand fetches.
- Errors are logged as warnings (`Harvesting <source> failed`), and kept in `harvest_sources.last_error`.
- To run one tick by hand (the scheduler may run meanwhile: SKIP LOCKED keeps them apart):

  ```sh
  uv run --frozen python - <<'EOF'
  from sqlalchemy import engine_from_config
  from c2corg_api.config import get_appsettings
  from c2corg_api.harvest import runner
  from c2corg_api.models import DBSession

  settings = get_appsettings('development.ini')
  DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))
  runner.harvest_tick({**settings, 'harvest.enabled': 'true'}, workers=1)
  EOF
  ```

  It fetches only the due sources: to fetch some now, `UPDATE guidebook.harvest_sources SET next_run_at = now() WHERE
  harvester = 'avalanche.caaml';` first.
