"""
The timetable of a cluster of stops: the details of its stops (they come from
several feeds, with their own day masks and first day) put together.
"""
from datetime import date

from c2corg_api.transport.dedup import name_tokens
from c2corg_api.transport.gtfs import SERVICE_DAYS


def _days_between(first, second):
    return (date.fromisoformat(second) - date.fromisoformat(first)).days


def line_key(line):
    """The same line in two feeds: same mode and same code."""
    return line['mode'], ' '.join(sorted(name_tokens(line['short_name']))) \
        or line['short_name'].strip().lower()


def merge_details(members):
    """
    Puts together the details of stops.

    `members`: [(feed_id, details)], the first one is the anchor of the
    cluster. Returns the details: `start`, `services` and `lines`, as a stop
    has them, plus the `feed_id` of the member each line comes from.

    Lines of the same mode and code are one line, and a departure of two
    members (same time, same direction, days that overlap) is shown once, on
    the days of both.
    """
    if len(members) == 1:
        feed_id, details = members[0]
        return {
            **details,
            'lines': [dict(line, feed_id=feed_id) for line in details['lines']]
        }

    start = min(details['start'] for _, details in members)
    shifts = [_days_between(start, details['start']) for _, details in members]
    # the days all the members have timetables for: two departures at the
    # same time are the same if they run some days there
    first = max(shifts)
    last = min(shift + SERVICE_DAYS for shift in shifts)
    common = ((1 << max(0, last - first)) - 1) << first

    lines = {}
    for (feed_id, details), shift in zip(members, shifts):
        for line in details['lines']:
            merged = lines.setdefault(line_key(line), {
                key: value for key, value in line.items()
                if key not in ('departures', 'headsigns')
            } | {'feed_id': feed_id, 'headsigns': [], 'departures': {}})
            for minutes, service, headsign in line['departures']:
                mask = int(details['services'][service], 16) << shift
                name = line['headsigns'][headsign]
                if name not in merged['headsigns']:
                    merged['headsigns'].append(name)
                same = merged['departures'].setdefault(
                    (minutes, merged['headsigns'].index(name)), [])
                for entry in same:
                    if entry['mask'] & mask & common:
                        entry['mask'] |= mask
                        break
                else:
                    same.append({'mask': mask})

    services = {}  # day mask -> key
    for line in lines.values():
        departures = []
        for (minutes, headsign), entries in sorted(line['departures'].items()):
            for entry in entries:
                key = services.setdefault('%x' % entry['mask'],
                                          's%d' % len(services))
                departures.append([minutes, key, headsign])
        line['departures'] = departures

    return {
        'start': start,
        'services': {key: mask for mask, key in services.items()},
        'lines': list(lines.values()),
    }
