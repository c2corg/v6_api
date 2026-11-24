# Partner outings

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
