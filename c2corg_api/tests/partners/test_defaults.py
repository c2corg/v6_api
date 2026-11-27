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
    assert env['harvest_partners_enabled'] == 'false'
    assert env['partners_transport'] == 'http'
    assert env['partners_allow_synthetic'] == 'false'
    assert env['partners_lookup_retention'] == '30'
    # empty: the outings are kept forever (the API lists 31 days at most)
    assert env['partners_retention'] == ''


def test_only_the_dev_stack_allows_synthetic_fixtures():
    assert read_env('env.dev')['partners_allow_synthetic'] == 'true'
    for name in ('env.demo', 'env.test', 'env.devcontainer', 'env.local.sample'):
        assert 'partners_allow_synthetic' not in read_env(name), name


def test_each_source_has_its_switch():
    from c2corg_api.partners.sources import REGISTRY

    env = read_env('env.default')
    template = (CONFIG.parent / 'common.ini.in').read_text(encoding='utf-8')
    for name in REGISTRY:
        key = f'harvest_partners_{name}_enabled'
        assert key in env, name
        assert f'harvest.partners.{name}.enabled = {{{key}}}' in template, name


def test_new_sources_are_off_by_default():
    # off even when harvest_partners_enabled is switched on, until the site
    # agrees; the dev stack runs them on the fixtures
    env = read_env('env.default')
    dev = read_env('env.dev')
    for name in ('bivouak', 'gipfelbuch', 'skitourenportal'):
        assert env[f'harvest_partners_{name}_enabled'] == 'false', name
        assert dev[f'harvest_partners_{name}_enabled'] == 'true', name


def test_the_test_config_switches_every_partner_source_off():
    # the CI renders env.default, env.dev then env.test: a source env.dev
    # switches on must be reset there, or the scheduler tests see it on
    rendered = {
        **read_env('env.default'),
        **read_env('env.dev'),
        **read_env('env.test'),
    }
    for key, value in rendered.items():
        if key.startswith('harvest_partners_') and key.endswith('_enabled'):
            assert value in ('', 'false'), key
