"""The partners package stays free of the web framework and the database."""

import ast
from pathlib import Path

import c2corg_api.partners

FORBIDDEN = (
    'fastapi',
    'starlette',
    'sqlalchemy',
    'pyramid',
    'geoalchemy2',
    'c2corg_api.models',
    'c2corg_api.web',
    'c2corg_api.views',
)
ALLOWED = ('c2corg_api.models.common.attributes',)


def _imports(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            module = node.module or ''
            yield module
            # `from c2corg_api import models`
            for alias in node.names:
                yield f'{module}.{alias.name}'


def _forbidden(name):
    if name in ALLOWED or name.startswith(tuple(a + '.' for a in ALLOWED)):
        return False
    return any(name == f or name.startswith(f + '.') for f in FORBIDDEN)


def _modules():
    root = Path(c2corg_api.partners.__file__).parent
    return sorted(root.rglob('*.py'))


def test_there_are_modules_to_check():
    names = {p.name for p in _modules()}
    assert {'model.py', 'adapter.py', 'transport.py', 'normalise.py'} <= names


def test_no_forbidden_imports():
    offending = [
        f'{path.name}: {name}'
        for path in _modules()
        for name in _imports(path)
        if _forbidden(name)
    ]
    assert offending == []


def test_checker_detects_forbidden_imports(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        'import sqlalchemy.orm\n'
        'from c2corg_api.models import document\n'
        'from c2corg_api import models\n'
        'from fastapi import FastAPI\n'
        'from c2corg_api.models.common.attributes import ski_ratings\n'
    )
    found = {n for n in _imports(bad) if _forbidden(n)}
    assert 'sqlalchemy.orm' in found
    assert 'c2corg_api.models' in found
    assert 'c2corg_api.models.document' in found
    assert 'fastapi' in found
    assert not _forbidden('c2corg_api.models.common.attributes')
