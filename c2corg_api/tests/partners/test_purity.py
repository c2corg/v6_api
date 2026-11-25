"""The partners package stays free of the web framework and the database.

An allow-list, not a deny-list: besides the standard library, the package may
only import `requests`, `bs4` (the HTML parser), itself and the attribute
constants. Anything new (sqlalchemy, c2corg_api.jobs, c2corg_api.caching,
elasticsearch...) fails.
"""

import ast
import sys
from pathlib import Path

import c2corg_api.partners

ALLOWED = (
    'requests',
    'bs4',
    'c2corg_api.partners',
    'c2corg_api.models.common.attributes',
)
ROOT = Path(c2corg_api.partners.__file__).parent


def _package(path):
    """The dotted package of a module of c2corg_api.partners."""
    parts = path.relative_to(ROOT.parent.parent).with_suffix('').parts
    return '.'.join(parts if path.name == '__init__.py' else parts[:-1])


def _imports(path, package):
    """Yield `(name, is_from_module)` for each import of a module.

    For `from a.b import c`, `a.b` is yielded with `is_from_module` (it may be
    a parent of an allowed module) and `a.b.c` without (it must be allowed
    itself: `from c2corg_api import models` is caught).
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, False
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:
                base = package.split('.')
                base = base[: len(base) - node.level + 1]
                module = '.'.join([*base, module] if module else base)
            yield module, True
            for alias in node.names:
                yield f'{module}.{alias.name}', False


def _allowed(name, is_from_module=False):
    if name.split('.')[0] in sys.stdlib_module_names:
        return True
    if any(name == a or name.startswith(a + '.') for a in ALLOWED):
        return True
    # `from c2corg_api.models.common import attributes`
    return is_from_module and any(a.startswith(name + '.') for a in ALLOWED)


def _forbidden(path, package):
    return {
        name for name, is_from in _imports(path, package) if not _allowed(name, is_from)
    }


def _modules():
    return sorted(ROOT.rglob('*.py'))


def test_there_are_modules_to_check():
    names = {p.name for p in _modules()}
    assert {'model.py', 'adapter.py', 'transport.py', 'normalise.py'} <= names


def test_no_forbidden_imports():
    offending = [
        f'{path.relative_to(ROOT)}: {name}'
        for path in _modules()
        for name in sorted(_forbidden(path, _package(path)))
    ]
    assert offending == []


def test_checker_detects_forbidden_imports(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        'import sqlalchemy.orm\n'
        'from c2corg_api.models import DBSession\n'
        'from c2corg_api import models\n'
        'from fastapi import FastAPI\n'
        'from c2corg_api.jobs import scheduler\n'
        'from ... import caching\n'
        'from ...models.document import Document\n'
        'import c2corg_api\n'
    )
    assert _forbidden(bad, 'c2corg_api.partners.sources') == {
        'sqlalchemy.orm',
        'c2corg_api.models.DBSession',
        'c2corg_api.models',
        'fastapi',
        'fastapi.FastAPI',
        'c2corg_api.jobs',
        'c2corg_api.jobs.scheduler',
        'c2corg_api.caching',
        'c2corg_api.models.document',
        'c2corg_api.models.document.Document',
        'c2corg_api',
    }


def test_checker_accepts_allowed_imports(tmp_path):
    good = tmp_path / 'good.py'
    good.write_text(
        'import json, requests.adapters\n'
        'from collections.abc import Mapping\n'
        'from c2corg_api.models.common.attributes import ski_ratings\n'
        'from c2corg_api.models.common import attributes\n'
        'from c2corg_api.partners.model import RateLimit\n'
        'from .. import normalise\n'
        'from ..transport import HttpTransport\n'
    )
    assert _forbidden(good, 'c2corg_api.partners.sources') == set()
