from datetime import UTC, datetime, time, timedelta

import pytest

from c2corg_api.avalanche_bulletins.harvesters import AVALANCHE_POLICY
from c2corg_api.harvest.policy import PARIS, Policy, Window, next_run


def paris(*args, **kwargs):
    return datetime(*args, tzinfo=PARIS, **kwargs)


@pytest.mark.parametrize(
    ('now', 'published', 'expected'),
    [
        # in a window: every 15 minutes until a new publication, then hourly
        (paris(2026, 11, 24, 8), False, paris(2026, 11, 24, 8, 15)),
        (paris(2026, 11, 24, 9, 55), False, paris(2026, 11, 24, 10, 10)),
        (paris(2026, 11, 24, 8), True, paris(2026, 11, 24, 9)),
        (paris(2026, 11, 24, 16), True, paris(2026, 11, 24, 17)),
        # hourly outside, up to the start of the next window
        (paris(2026, 11, 24, 11), False, paris(2026, 11, 24, 12)),
        (paris(2026, 11, 24, 11), True, paris(2026, 11, 24, 12)),
        (paris(2026, 11, 24, 14, 50), False, paris(2026, 11, 24, 15, 30)),
        (paris(2026, 11, 24, 6, 30), False, paris(2026, 11, 24, 7)),
        (paris(2026, 11, 24, 19), False, paris(2026, 11, 24, 20)),
        (paris(2026, 11, 24, 23, 30), False, paris(2026, 11, 25, 0, 30)),
        # the season, both days included
        (paris(2026, 6, 30, 12), False, paris(2026, 6, 30, 13)),
        (paris(2026, 11, 1, 12), False, paris(2026, 11, 1, 13)),
        # out of season: once a day, at the start of the first window
        (paris(2026, 7, 1, 8), False, paris(2026, 7, 2, 7)),
        (paris(2026, 7, 15, 6), False, paris(2026, 7, 15, 7)),
        (paris(2026, 7, 15, 7), True, paris(2026, 7, 16, 7)),
        # the first day of the season (and of winter time)
        (paris(2026, 10, 31, 7), False, paris(2026, 11, 1, 7)),
        # the night of summer time: 7:00 is 5:00 UTC
        (paris(2026, 3, 29, 6, 30), False, paris(2026, 3, 29, 7)),
    ],
)
def test_next_run(now, published, expected):
    when = next_run(AVALANCHE_POLICY, now, now if published else None)
    assert when == expected
    assert when.tzinfo == UTC


@pytest.mark.parametrize(
    ('last_publication', 'expected'),
    [
        # earlier in the window: still hourly
        (paris(2026, 11, 24, 7, 10), paris(2026, 11, 24, 9, 30)),
        # in the window of the day before, or the one of the morning: not this one
        (paris(2026, 11, 23, 8), paris(2026, 11, 24, 8, 45)),
        (paris(2026, 11, 23, 16), paris(2026, 11, 24, 8, 45)),
    ],
)
def test_slower_after_a_publication(last_publication, expected):
    now = paris(2026, 11, 24, 8, 30)
    assert next_run(AVALANCHE_POLICY, now, last_publication) == expected


def test_new_window_after_a_publication():
    published = paris(2026, 11, 24, 8)
    now = paris(2026, 11, 24, 16)
    assert next_run(AVALANCHE_POLICY, now, published) == paris(2026, 11, 24, 16, 15)


def test_summer_time_in_utc():
    # 1:30 + 1 hour: 3:30 of summer time
    now = paris(2026, 3, 29, 1, 30)
    assert next_run(AVALANCHE_POLICY, now) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert next_run(AVALANCHE_POLICY, paris(2026, 3, 29, 6, 30)) == datetime(
        2026, 3, 29, 5, tzinfo=UTC
    )


def test_winter_time_hour_repeated():
    # 2:30 comes twice on 2026-10-25: an hour later is the second one
    policy = Policy(windows=(Window(time(7), time(10), 15),))
    first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert first.astimezone(PARIS).time() == time(2, 30)
    assert next_run(policy, first) == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    # the next window, in winter time
    assert next_run(policy, paris(2026, 10, 25, 6, 30)) == datetime(
        2026, 10, 25, 6, tzinfo=UTC
    )


def test_without_windows():
    policy = Policy(default_every=30)
    now = paris(2026, 11, 24, 8)
    assert next_run(policy, now, now) == paris(2026, 11, 24, 8, 30)


def test_without_slowdown():
    policy = Policy(
        windows=(Window(time(7), time(10), 15),), after_publication_every=None
    )
    now = paris(2026, 11, 24, 8)
    assert next_run(policy, now, now) == paris(2026, 11, 24, 8, 15)


@pytest.mark.parametrize(
    ('error_count', 'expected'),
    [
        (1, paris(2026, 11, 24, 8, 15)),
        (2, paris(2026, 11, 24, 8, 30)),
        (3, paris(2026, 11, 24, 9)),
        (5, paris(2026, 11, 24, 12)),
        (50, paris(2026, 11, 24, 12)),
    ],
)
def test_backoff_doubles_up_to_max(error_count, expected):
    assert next_run(AVALANCHE_POLICY, paris(2026, 11, 24, 8), None, error_count) == (
        expected
    )


def test_backoff_never_sooner():
    # out of season, the next check stays the next day
    now = paris(2026, 7, 15, 8)
    assert next_run(AVALANCHE_POLICY, now, None, 1) == paris(2026, 7, 16, 7)


def test_jitter():
    now = paris(2026, 11, 24, 8)
    assert next_run(AVALANCHE_POLICY, now, rand=0.5) == paris(
        2026, 11, 24, 8, 15
    ) + timedelta(seconds=30)


@pytest.mark.parametrize(
    ('season', 'day', 'expected'),
    [
        (((11, 1), (6, 30)), (12, 31), True),
        (((11, 1), (6, 30)), (1, 1), True),
        (((11, 1), (6, 30)), (7, 1), False),
        (((11, 1), (6, 30)), (10, 31), False),
        (((3, 1), (9, 30)), (3, 1), True),
        (((3, 1), (9, 30)), (10, 1), False),
        (None, (8, 15), True),
    ],
)
def test_in_season(season, day, expected):
    policy = Policy(season=season)
    assert policy.in_season(datetime(2026, *day).date()) is expected
