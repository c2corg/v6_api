import dataclasses
import datetime
from collections import Counter

import pytest

from c2corg_api.partners.adapter import (
    ParseError,
    SourceBlocked,
    SourceDisabled,
    SourceDown,
    require_secrets,
)
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import (
    FetchContext,
    FetchResult,
    HarvestedOuting,
    RateLimit,
)
from c2corg_api.partners.sources import REGISTRY, SOURCE_NAMES


def context(secrets):
    return FetchContext(
        since=datetime.date(2026, 1, 1),
        now=datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC),
        cursor=None,
        transport=None,
        lookups=MemoryLookupCache(),
        secrets=secrets,
    )


def outing(**kwargs):
    values = {
        'source': 'skitour',
        'external_id': '1',
        'url': 'https://skitour.fr/sorties/1',
        'title': 'Trip',
        'date': datetime.date(2026, 1, 1),
        'activities': ('skitouring',),
    }
    return HarvestedOuting(**{**values, **kwargs})


def test_source_names_come_from_the_registry():
    assert (
        SOURCE_NAMES
        == tuple(REGISTRY)
        == (
            'skitour',
            'gulliver',
            'bivouak',
            'gipfelbuch',
            'skitourenportal',
        )
    )


@pytest.mark.parametrize('name', sorted(REGISTRY))
def test_every_source_has_a_credit(name):
    adapter = REGISTRY[name]
    assert adapter.name == name
    assert adapter.site_name.strip()
    assert adapter.site_url.startswith('https://')


def test_harvested_outing_defaults_and_is_frozen():
    o = outing()
    assert o.steep is False
    assert o.orientations == ()
    assert o.geom_quality == 'none'
    assert o.snow is None
    assert not hasattr(o, '__dict__')
    with pytest.raises(dataclasses.FrozenInstanceError):
        o.title = 'other'


def test_fetch_result_defaults_are_not_shared():
    a, b = FetchResult(outings=[]), FetchResult(outings=[])
    a.skipped['too_old'] += 1
    a.outings.append(outing())
    assert isinstance(b.skipped, Counter)
    assert b.skipped == Counter()
    assert b.outings == []
    assert (b.cursor, b.item_errors) == (None, 0)


def test_rate_limit_is_frozen():
    rate = RateLimit(1.0, 10, 5.0)
    assert (rate.min_interval_s, rate.max_requests_per_run, rate.timeout_s) == (
        1.0,
        10,
        5.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rate.timeout_s = 1


def test_fetch_context_now_must_be_aware():
    with pytest.raises(ValueError, match='aware'):
        FetchContext(
            since=datetime.date(2026, 1, 1),
            now=datetime.datetime(2026, 1, 2),
            cursor=None,
            transport=None,
            lookups=MemoryLookupCache(),
            secrets={},
        )


def test_require_secrets():
    require_secrets(context({'A': '1', 'B': '2'}), ('A', 'B'))
    with pytest.raises(SourceDisabled, match='^B not set$'):
        require_secrets(context({'A': '1'}), ('A', 'B'))
    with pytest.raises(SourceDisabled, match='A not set'):
        require_secrets(context({'A': ''}), ['A'])


def test_exceptions_are_distinct():
    classes = {SourceDisabled, SourceBlocked, SourceDown, ParseError}
    for cls in classes:
        assert issubclass(cls, Exception)
        assert not any(issubclass(cls, other) for other in classes - {cls})


def test_memory_lookup_cache():
    cache = MemoryLookupCache()
    assert cache.get('k') is None
    data = {'a': [1]}
    cache.put('k', data)
    data['a'].append(2)  # the cache keeps its own copy
    assert cache.get('k') == {'a': [1]}
    cache.get('k')['a'].append(3)
    assert cache.get('k') == {'a': [1]}
    cache.put('k', {'b': 1})
    assert cache.get('k') == {'b': 1}


def test_memory_lookup_cache_behaves_like_jsonb():
    cache = MemoryLookupCache()
    cache.put('k', {'coords': (6.8, 45.8)})
    assert cache.get('k') == {'coords': [6.8, 45.8]}
    with pytest.raises(TypeError):
        cache.put('k', {'when': datetime.date(2026, 1, 1)})
