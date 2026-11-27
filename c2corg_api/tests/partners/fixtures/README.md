# Partner fixtures

Each partner source has a directory `fixtures/<source>/` read by
`FixtureTransport` (`c2corg_api/partners/transport.py`). Tests and the local
demo (`transport=fixtures`) never touch the network.

## Layout

```
fixtures/<source>/manifest.json
fixtures/<source>/<endpoint>_<distinguishing params>.<json|html>
```

File names are snake case: `sorties_j2_c1_l200.json`, `routes_id57949.json`,
`verhaeltnisse.html`.

`manifest.json`:

```json
{"source": "gulliver", "recorded_at": "2026-11-24", "synthetic": true,
 "note": "built from DATA_SOURCES.md 1.3; site behind a Cloudflare challenge from the sandbox",
 "entries": [{"url": "https://www.gulliver.it/wp-json/gulliver/mobile/commentglobal",
              "params": {"page": "1"}, "status": 200,
              "content_type": "application/json", "file": "commentglobal_page1.json"}]}
```

Matching: same scheme, host and path, and every param of the entry (compared
as strings) present in the request. The matching entry with the most params
wins, so an entry without params is a fallback for that path; on a tie, the
first one. No match
raises `SourceDown('no fixture for ...')`, so a test fails loudly. The entry
`status` is honoured and classified like a live response: an entry with
`"status": 403` (and a Cloudflare body) simulates a block, `503` a down site.

## The `synthetic` flag

`"synthetic": true` means the files were written by hand from the documented
field lists (DATA_SOURCES.md 1.2 and 1.3), because the site could not be
reached when the fixtures were made. A synthetic fixture proves that the
adapter parses the documented format, not that the live format is the same.
Re-record it with `python -m c2corg_api.partners record <source>` from a
machine that reaches the site (recorded manifests have `"synthetic": false`
and the recording date), then review the diff and run `python -m
c2corg_api.partners shapes` to see what changed.

## Network status (design section 2, 2026-11-24)

| Source | From the dev sandbox | Fixtures in M1 |
|---|---|---|
| skitour.fr | reachable with an API key (`cle` header, `SKITOUR_API_KEY` or `SKITOUR_API_KEY_FILE`) | recorded 2026-11-25 (`skitour/`, `synthetic: false`) |
| gulliver.it | 403 Cloudflare "Just a moment..." JS challenge from cloud addresses; reachable from a home connection (camptocamp User-Agent) | recorded 2026-11-27 (`gulliver/`, texts redacted, authors pseudonymised) + `gulliver_synthetic/` |
| gipfelbuch.ch | reachable | recorded 2026-11-25 (HTML, trimmed to the selectors of the adapter) |
| bivouak.net | reachable | recorded 2026-11-25 (HTML, trimmed to the selectors of the adapter) |
| skitourenportal.eu | reachable without `www` | recorded 2026-11-25 (HTML, trimmed to the selectors, authors pseudonymised) |
| on-ice.it | blocked by the sandbox proxy | not yet (later) |
| api.camptocamp.org | reachable | not needed |

Never commit an API key or a cookie in a fixture.

No partner free text either (comments, narratives, conditions, access notes, photos,
tracks): a fixture only holds the paths the adapter reads (`REQUIRED_PATHS`), and the
texts it reads (to store them, never to serve them) are replaced by placeholders,
`[text 491 chars]` (`REDACT_PATHS`, `REDACT_SELECTORS`). The recorder enforces it, and
`test_fixtures_have_no_free_text` checks the committed files.
Fixture mode refuses a `synthetic: true` manifest unless `partners.allow_synthetic` is true (dev only).

## Real recordings of error answers

`skitour_no_key/` and `skitour_bad_key/` (`synthetic: false`) are curl
recordings of what skitour.fr answers to a request without a key, or with a
rejected one: HTTP 200 and `{"ERROR": "NO API KEY"}` / `{"ERROR": "INVALID API
KEY"}` instead of a list. `SkitourAdapter` turns them into `SourceBlocked`
(status `blocked`, detail `skitour API error: <message>`). They are separate
directories so that `record skitour` never overwrites them.

## skitour: real recording and synthetic edge cases

`skitour/` is a real recording (2026-11-25, `python -m c2corg_api.partners record
skitour`, 1 request, trimmed to `REQUIRED_PATHS`: no `recit`, `cond`, `photos`,
`participants`, `topos`, `gpx`; the `cle` header is never recorded). Real format:
every value is a string, `date` an epoch at 00:00 Paris time, coordinates
`lat`/`lng`, the start point `depart`, `sommets` may be missing or null.
The author pseudos are replaced by `user1`, `user2`... (`PSEUDONYMISE_PATHS`); the titles are what the adapter reads.

`skitour_synthetic/` (`synthetic: true`, note starts with `SYNTHETIC EDGE CASES`)
is hand-written in the same format for what the recording does not hold: broken
items, odd dates, HTML entities, invalid coordinates, ties, paging. It is only
used by `tests/partners/test_skitour.py`; it is not a recording, never re-record it.

## HTML fixtures (bivouak)

`fixtures/bivouak/` holds HTML pages, trimmed by `htmlparse.trim` to what `REQUIRED_SELECTORS` match: no excerpt, no
photo, no script. The authors (`PSEUDONYMISE_SELECTORS`: name and profile link) are replaced by `user1`, `user2`...
(the HTML counterpart of `PSEUDONYMISE_PATHS`). `shape.json` lists, per file, the selectors that matched. The recording was made once (15 requests,
10 s apart, with the camptocamp User-Agent; robots.txt allows these paths) and parsed offline. One file,
`sortie_30886.html`, comes from a copy of the page saved during the same session (the first recording stopped on an
untitled outing: the adapter was fixed to give it a title and its detail page was then added by hand, trimmed the same
way). `record bivouak --since 2026-02-15` is how to refresh them; a recording from a later day has other outings, so the
assertions of `test_bivouak.py` on counts and ids change with it.

## gulliver: real recording and synthetic edge cases

`gulliver/` is a real recording (2026-11-27, `python -m c2corg_api.partners record gulliver --since 2026-09-20`,
44 requests): the 5 pages of `commentglobal`, the front page fragment (`comments_sortingid.json`: the JSON with its
HTML trimmed to the report links), 14 reports read with `comments?id=` and the 24 routes of the ski reports. The texts
are `[text N chars]`, the authors `user1`, `user2`...; of the tracks only the GPX links are kept. The early `--since`
makes the recording hold every report the front page links to, so that the job of the demo (which asks 16 days back)
finds them all; `shapes --offline` replays it with the default 7 days. `challenge_403.html` is a Cloudflare page kept
by hand for the block tests (also used by the bivouak tests).

`gulliver_synthetic/` (`synthetic: true`, note starts with `SYNTHETIC EDGE CASES`) is hand-written in the same format
for what the recording does not hold: a steep grade, an empty route skeleton, unsafe GPX links, broken items, a failing
route, an empty report detail. It is only used by `tests/partners/test_gulliver.py`; never re-record it.

## gulliver_tracks: synthetic GPX files

`gulliver_tracks/` (`synthetic: true`) is read by the track phase in fixture mode (`<source>_tracks/`): made-up GPX
loops at the GPX links of the three newest reports with a GPX of the `gulliver/` recording, one of them with a fake
time, heart rate and author (the reader must drop them). Real GPX files of the users are never committed: they hold
personal data (times, heart rates).
