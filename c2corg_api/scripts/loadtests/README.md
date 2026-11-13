Load tests with Locust
======================

`locustfile.py` holds the load test scenarios of the API for [Locust](https://locust.io/). The test users are of two kinds:
- **Visitor** (9 in 10): an anonymous visitor reading the guidebook (documents, cooked documents, listings, search, history, the feed).
- **Contributor** (1 in 10): a logged-in user who also reads their account, preferences and personal feed. With `C2C_WRITES=1`, the contributor also follows and unfollows other test users; these writes leave no trace.

The document ids come from the listings of the API when the test starts.

Run them against a staging copy of the API with production-like data, never against production.

Running
-------

Locust runs in its own environment: the project holds urllib3 below 2 (Elasticsearch 2.4), which Locust does not support. With [uv](https://docs.astral.sh/uv/), from the root of the repository:

    uvx --from locust==2.46.7 locust -f c2corg_api/scripts/loadtests/locustfile.py --host https://api.staging.example

Then open <http://localhost:8089> to start a test, and watch the statistics and charts as it runs.

Without the web UI, e.g. 200 users, 10 more per second, for 10 minutes, with the results in CSV files and an HTML report:

    uvx --from locust==2.46.7 locust -f c2corg_api/scripts/loadtests/locustfile.py --host https://api.staging.example \
        --headless -u 200 -r 10 -t 10m --csv results/run1 --html results/run1.html

Settings, through environment variables:
- `C2C_USERNAME` (default `testuserc2c`) and `C2C_USERS` (default `1000`): the test accounts, `<C2C_USERNAME><1 to C2C_USERS>`, whose password is their username.
- `C2C_WRITES=1`: also send the writes of the contributors.

To compare two versions of the API, run the same test twice against each version, on the same data, and compare the percentiles.

Setting up the target
---------------------

- **Test accounts:** `create_test_users.py` creates 1000 validated accounts, `testuserc2c1` to `testuserc2c1000`, with their username as password. It reads the database URL from `loadtests.ini`, made from `loadtests.ini.in` like the other `.ini` files. Then run:

      python c2corg_api/scripts/loadtests/create_test_users.py

- **Rate limiting:** the logins are rate limited per client IP (`rate_limiting.anonymous_limit` per `rate_limiting.anonymous_window_span` seconds, 20 per 15 minutes by default). All the Locust users come from the same IP, so raise the limit on the target. With `C2C_WRITES=1`, the writes of each account are also rate limited (`rate_limiting.limit`).

Quick comparisons
-----------------

`scripts/loadtest.py` (standard library only) replays a mix of reads with a few threads, to compare two versions of the API on a development machine (see HOWTO-DEV).
