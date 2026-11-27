"""The shipped defaults: every partner source on, nothing purged, fixtures safe."""

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
    assert env['harvest_partners_enabled'] == 'true'
    assert env['partners_transport'] == 'http'
    assert env['partners_allow_synthetic'] == 'false'
    # a cache of the partner sites, not data
    assert env['partners_lookup_retention'] == '30'


def test_env_default_never_purges_the_outings():
    """No 31-day (or any) retention: the outings and their tracks stay forever.

    The API lists 31 days at most per query: a display window, not a retention.
    """
    from c2corg_api.jobs.harvest_partner_outings import _retention_days

    for name in ('env.dev', 'env.test', 'env.demo', 'env.devcontainer'):
        assert 'partners_retention' not in read_env(name), name
    value = read_env('env.default')['partners_retention']
    assert value == ''
    assert _retention_days({'partners.retention_days': value}) is None


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


def test_every_source_is_on_by_default():
    # each source follows harvest_partners_enabled ("true"), in production and
    # in the dev stack (on the fixtures there)
    from c2corg_api.harvest.runner import harvest_enabled
    from c2corg_api.jobs.harvest_partner_outings import enabled_sources
    from c2corg_api.partners.sources import REGISTRY

    for rendered in (
        read_env('env.default'),
        {**read_env('env.default'), **read_env('env.dev')},
    ):
        settings = {
            'harvest.enabled': rendered['harvest_enabled'],
            'harvest.partners.enabled': rendered['harvest_partners_enabled'],
            **{
                f'harvest.partners.{name}.enabled': rendered.get(
                    f'harvest_partners_{name}_enabled', ''
                )
                for name in REGISTRY
            },
        }
        assert harvest_enabled(settings, 'partners.skitour')
        assert enabled_sources(settings) == list(REGISTRY)


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
