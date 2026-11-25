"""Maintainer CLI: re-record the partner fixtures, check the partner APIs.

    python -m c2corg_api.partners record <source> [--out DIR] [--since DATE]
    python -m c2corg_api.partners shapes <source> [--offline] [--fixtures DIR]

Exit codes: 0 fine, 1 the partner changed something the adapter relies on
(or the adapter could not parse the answer), 2 the check could not run (site
blocked or down, secret missing, no fixture shapes to compare with).
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from c2corg_api.partners import contract
from c2corg_api.partners.adapter import (
    ParseError,
    SourceBlocked,
    SourceDisabled,
    SourceDown,
)
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import (
    FixtureTransport,
    HttpTransport,
    RecordingTransport,
    Transport,
)

# the committed fixtures: <repo>/c2corg_api/tests/partners/fixtures
DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent / 'tests/partners/fixtures'
DEFAULT_DAYS = 7
EXIT_OK, EXIT_BREAKING, EXIT_UNAVAILABLE = 0, 1, 2


def make_transport(adapter) -> Transport:
    """Return the transport of a live run; tests replace it with a fake."""
    return HttpTransport(adapter.rate)


def _secret(name: str) -> str | None:
    """Return `$NAME`, else the content of the file `$NAME_FILE` (never logged)."""
    value = os.environ.get(name)
    if value:
        return value
    path = os.environ.get(f'{name}_FILE')
    if not path:
        return None
    try:
        return Path(path).read_text(encoding='utf-8').strip() or None
    except OSError:
        return None


def secrets_from_env(adapter) -> dict[str, str]:
    """Read the adapter secrets from the environment or the `*_FILE` files."""
    values = {name: _secret(name) for name in adapter.required_secrets}
    return {name: value for name, value in values.items() if value}


def _date(text: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f'{text!r} is not a YYYY-MM-DD date') from e


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python -m c2corg_api.partners',
        description='Re-record partner fixtures and check partner API shapes.',
    )
    commands = parser.add_subparsers(dest='command', required=True)
    sources = sorted(REGISTRY)

    record = commands.add_parser(
        'record', help='run the adapter live and write the fixtures'
    )
    record.add_argument('source', choices=sources)
    record.add_argument(
        '--out',
        type=Path,
        default=DEFAULT_FIXTURES,
        help='fixtures root; files go to <out>/<source>/ (default: the tests fixtures)',
    )
    record.add_argument(
        '--since',
        type=_date,
        help=f'oldest outing date wanted (default: {DEFAULT_DAYS} days ago)',
    )

    check = commands.add_parser(
        'shapes', help='diff the live answer shapes against the fixtures'
    )
    check.add_argument('source', choices=sources)
    check.add_argument(
        '--fixtures',
        type=Path,
        default=DEFAULT_FIXTURES,
        help='fixtures root to compare with (default: the tests fixtures)',
    )
    check.add_argument(
        '--offline',
        action='store_true',
        help='replay the fixtures instead of calling the site (a self-check)',
    )
    check.add_argument('--since', type=_date, help='as for record')
    return parser


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


def _install(work: Path, target: Path) -> list[str]:
    """Move the recorded files into `target`; return their names.

    Files listed by the previous manifest and not recorded again are removed;
    any other file of the directory (hand-made fixtures) is left alone.
    """
    target.mkdir(parents=True, exist_ok=True)
    new = sorted(p.name for p in work.iterdir())
    old_manifest = target / 'manifest.json'
    if old_manifest.exists():
        for entry in json.loads(old_manifest.read_text(encoding='utf-8')).get(
            'entries', []
        ):
            name = entry.get('file')
            if name and name not in new:
                (target / name).unlink(missing_ok=True)
    for name in new:
        shutil.move(str(work / name), str(target / name))
    return new


def cmd_record(args) -> int:
    adapter = REGISTRY[args.source]()
    since = args.since or _today() - datetime.timedelta(days=DEFAULT_DAYS)
    args.out.mkdir(parents=True, exist_ok=True)
    # record aside: a run that fails leaves the existing fixtures untouched
    work = Path(tempfile.mkdtemp(prefix=f'.recording-{args.source}-', dir=args.out))
    try:
        transport = RecordingTransport(
            make_transport(adapter),
            work,
            args.source,
            trim=partial(contract.trim_body, args.source, names={}),
            ignore_params=contract.VOLATILE_PARAMS.get(args.source, ()),
        )
        result = contract.run_adapter(
            adapter, transport, secrets_from_env(adapter), since
        )
        if not transport.entries:
            print(f'{args.source}: the adapter made no request', file=sys.stderr)
            return EXIT_BREAKING
        index = contract.write_shape_index(work / args.source)
        files = _install(work / args.source, args.out / args.source)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(
        f'{args.source}: recorded {len(transport.entries)} responses '
        f'({transport.request_count} requests) into {args.out / args.source}'
    )
    print(
        f'  adapter result: {len(result.outings)} outings, '
        f'{sum(result.skipped.values())} skipped, {result.item_errors} item errors'
    )
    print(f'  files: {", ".join(files)}')
    print(f'  shape.json: {len(index)} JSON files')
    print(
        '  review `git diff` before committing; payloads were trimmed '
        f'(lists cut to {contract.MAX_ITEMS} items, fields the adapter does not '
        'read and licensed texts dropped)'
    )
    return EXIT_OK


def cmd_shapes(args) -> int:
    adapter = REGISTRY[args.source]()
    directory = args.fixtures / args.source
    try:
        expected = contract.fixture_shapes(directory)
    except FileNotFoundError:
        print(
            f'{args.source}: no {contract.SHAPE_FILE} in {directory}; '
            f'run `record {args.source}` first',
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE

    secrets = secrets_from_env(adapter)
    if args.offline:
        transport = FixtureTransport(args.fixtures, args.source, rate=adapter.rate)
        recorded = datetime.date.fromisoformat(transport.recorded_at or '2000-01-01')
        now = datetime.datetime.combine(
            recorded, datetime.time(12), tzinfo=datetime.UTC
        )
        since = args.since or recorded - datetime.timedelta(days=2)
        # no key is needed to replay files
        secrets = {
            name: secrets.get(name, 'offline') for name in adapter.required_secrets
        }
    else:
        transport = make_transport(adapter)
        now = None
        since = args.since or _today() - datetime.timedelta(days=DEFAULT_DAYS)

    capture = contract.CapturingTransport(transport)
    result = contract.run_adapter(adapter, capture, secrets, since, now)
    actual = contract.captured_shapes(args.source, capture.responses)
    report = contract.compare(adapter, expected, actual)

    where = 'fixtures (offline)' if args.offline else 'live'
    print(
        f'{args.source}: {capture.request_count} requests {where}, '
        f'{len(result.outings)} outings parsed, {result.item_errors} item errors'
    )
    for endpoint, lines in report.diff.items():
        print(
            f'  {endpoint}: '
            + ('no change' if not lines else f'{len(lines)} differences')
        )
        for line in lines:
            print(f'    {line}')
    for endpoint in sorted(set(actual) - set(expected)):
        print(f'  {endpoint}: new endpoint, not in the fixtures')
    for line in report.unchecked:
        print(f'  unchecked: {line}')
    if report.breaking:
        print('BREAKING: the adapter reads fields that are gone or retyped:')
        for line in report.problems:
            print(f'  {line}')
        return EXIT_BREAKING
    print('OK: every field the adapter reads is still there')
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = cmd_record if args.command == 'record' else cmd_shapes
    try:
        return command(args)
    except SourceDisabled as e:
        print(f'{args.source}: disabled: {e}', file=sys.stderr)
    except SourceBlocked as e:
        print(f'{args.source}: blocked by the site: {e}', file=sys.stderr)
    except SourceDown as e:
        print(f'{args.source}: site unreachable or down: {e}', file=sys.stderr)
    except ParseError as e:
        print(
            f'{args.source}: the adapter cannot parse the answer: {e}',
            file=sys.stderr,
        )
        return EXIT_BREAKING
    return EXIT_UNAVAILABLE


if __name__ == '__main__':
    sys.exit(main())
