Outings scripts
===============

* `recompute_quality.py`: compute again the quality ("complétude") of the outings already saved, with the rules of the UI.
* `quality_rules.py`: those rules, in Python.

The quality of an outing
------------------------

The UI computes the quality of an outing when it is saved (`c2c_ui/src/js/document-quality.ts`), and again when images are added to it. The API does not compute it: it saves what the UI sends.

When the rules change in the UI, the outings saved before keep the quality of the old rules, until they are edited. `recompute_quality.py` gives them the quality of the new rules.

It keeps the quality an author chose: an outing is changed only when its quality is the one a version of the rules gives (in one of its locales). "Great" is never computed: it is always kept.

Each change is a new version of the outing (comment "Quality computed again with the rules of November 2026" by default), saved by the given user: it can be seen and reverted in the history. The caches of the outing and of the documents listing it (its routes, its users…) are invalidated, and the Elasticsearch syncer is notified.

| Version | Rules | Since |
|---|---|---|
| `quality_v1` | the rules of the UI until November 2026 | |
| `quality_v2` | never empty with a text; the track and the images count; the key information of each activity | c2c_ui#5065 |

Run it
------

Try first, without changing anything: it counts the outings that would change, by change (`empty -> draft: 1234`…):

    recompute_outing_quality production.ini --dry-run

On a few outings:

    recompute_outing_quality production.ini --user-id <id> --ids 123 456

On all of them (one transaction per batch of 500 outings: if it stops, run it again, it goes on):

    recompute_outing_quality production.ini --user-id <id>

`--user-id` is the account the new versions are saved by: a bot account, or a moderator. `--comment` changes the comment of the versions, `--batch-size` the size of the batches.

What it prints (the same with `--dry-run`, before anything is saved): the changes, then, by activity and by quality before the run, the outings that change out of all of them, as a markdown table (to paste in an issue or on the forum). An outing of several activities is counted in each of them, and once in the "all" row:

    3 outings changed, of 6 (50.0 %):
      empty -> draft: 1
      draft -> medium: 1
      fine -> medium: 1

    | activity | empty | draft | medium | fine | great | total |
    |---|---|---|---|---|---|---|
    | rock_climbing | 1 / 1 (100.0 %) | 1 / 2 (50.0 %) | - | 1 / 2 (50.0 %) | 0 / 1 (0.0 %) | 3 / 6 (50.0 %) |
    | **all** | 1 / 1 (100.0 %) | 1 / 2 (50.0 %) | - | 1 / 2 (50.0 %) | 0 / 1 (0.0 %) | 3 / 6 (50.0 %) |

`--csv changes.csv` also writes the outings that change, one per line (`document_id,activities,before,after`): to check a few of them by hand after a dry run.

In a docker environment:

    docker compose run --rm api recompute_outing_quality production.ini --dry-run

Without the installed command, `python -m c2corg_api.scripts.outings.recompute_quality production.ini …` does the same.

When the rules change again
---------------------------

1. Change the rules of the UI (`c2c_ui/src/js/document-quality.ts`) and their tests.
2. In `quality_rules.py`, add a function for the new rules at the end of `RULES`. Never change an existing one: the outings saved with it would look chosen, and be kept.
3. Add its cases to `c2corg_api/tests/scripts/outings/test_quality_rules.py`, the same as the UI tests (`c2c_ui/src/js/document-quality.spec.ts`).
4. Change `DEFAULT_COMMENT` in `recompute_quality.py`, and the table above.
5. Once the UI is deployed (the outings saved meanwhile get the new rules), run the script: `--dry-run` first.
