"""When to fetch a source again: more often when its service publishes."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')


@dataclass(frozen=True)
class Window:
    """A time of the day the service publishes, local time (end excluded)."""

    start: time
    end: time
    every_minutes: int


@dataclass(frozen=True)
class Policy:
    """The schedule of the sources of a harvester."""

    # (month, day) to (month, day), both included, maybe across the new
    # year; outside, one check a day (at the start of the first window)
    season: tuple | None = None
    windows: tuple = ()
    default_every: int = 60
    # once a window saw a new publication, an update is still possible but
    # rarer: this slower poll until the window ends (None: no slowdown)
    after_publication_every: int | None = 60
    # after errors, in minutes: min, doubled at each error up to max
    backoff_min: int = 15
    backoff_max: int = 240
    # spread the fetches, in seconds
    jitter: int = 60
    tz: ZoneInfo = PARIS

    def in_season(self, day):
        if self.season is None:
            return True
        start, end = self.season
        md = (day.month, day.day)
        if start <= end:
            return start <= md <= end
        return md >= start or md <= end


def next_run(policy, now, last_publication=None, error_count=0, rand=0.0):
    """Return when to fetch a source again (UTC), after a fetch at `now`.

    `last_publication`: when a new publication was last seen; `rand` in
    [0, 1) picks the jitter (random.random() by the runner, fixed by tests).
    """
    # the additions in UTC: a time of PARIS + timedelta is a wall-clock time,
    # wrong across a change of time
    now = now.astimezone(UTC)
    local = now.astimezone(policy.tz)
    jitter = timedelta(seconds=rand * policy.jitter)
    if not policy.in_season(local.date()):
        daily = policy.windows[0].start if policy.windows else time(0)
        when = _next_local(policy, now, [daily])
    else:
        window = next(
            (w for w in policy.windows if w.start <= local.time() < w.end), None
        )
        every = window.every_minutes if window else policy.default_every
        if window and policy.after_publication_every and last_publication:
            start = datetime.combine(local.date(), window.start, tzinfo=policy.tz)
            if last_publication >= start:
                every = policy.after_publication_every
        when = now + timedelta(minutes=every)
        # not past the start of a window
        following = _next_local(policy, now, [w.start for w in policy.windows])
        if following is not None:
            when = min(when, following)
    if error_count:
        backoff = policy.backoff_min * 2 ** min(error_count - 1, 16)
        # errors never bring the next fetch closer
        when = max(when, now + timedelta(minutes=min(backoff, policy.backoff_max)))
    return when + jitter


def _next_local(policy, now, times):
    # the first of these local times of the day after `now`, None without any
    if not times:
        return None
    day = now.astimezone(policy.tz).date()
    for days in range(3):
        candidates = [
            datetime.combine(day + timedelta(days=days), t, tzinfo=policy.tz)
            for t in sorted(times)
        ]
        later = [c.astimezone(UTC) for c in candidates if c.astimezone(UTC) > now]
        if later:
            return later[0]
    return None
