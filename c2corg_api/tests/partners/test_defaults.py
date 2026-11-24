"""The shipped defaults keep the partner harvest off and the fixtures safe."""

import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[3] / 'config'


def read_env(name):
    values = {}
    for line in (CONFIG / name).read_text(encoding='utf-8').splitlines():
        match = re.match(r'^(\w+)=["\']?([^"\']*)["\']?\s*(#.*)?$', line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def test_env_default_is_safe_for_production():
    env = read_env('env.default')
    assert env['partners_enabled'] == 'false'
    assert env['partners_transport'] == 'http'
    assert env['partners_allow_synthetic'] == 'false'
    assert env['partners_lookup_retention'] == '30'
    assert env['partners_retention'] == '31'


def test_only_the_dev_stack_allows_synthetic_fixtures():
    assert read_env('env.dev')['partners_allow_synthetic'] == 'true'
    for name in ('env.demo', 'env.test', 'env.devcontainer', 'env.local.sample'):
        assert 'partners_allow_synthetic' not in read_env(name), name
