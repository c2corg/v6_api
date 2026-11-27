from datetime import UTC, datetime
from unittest.mock import MagicMock

from c2corg_api.scripts.es import index_management as im


def _client(aliases=None, indices=()):
    """A fake client where `aliases` maps alias -> [index]."""
    aliases = aliases or {}
    client = MagicMock()
    client.indices.exists_alias.side_effect = lambda name: name in aliases
    client.indices.get_alias.side_effect = lambda name: {
        index: {'aliases': {name: {}}} for index in aliases[name]
    }
    client.indices.exists.side_effect = lambda index: index in indices
    return client


def test_new_index_name():
    now = datetime(2026, 11, 11, 8, 30, 5, tzinfo=UTC)
    assert im.new_index_name('c2corg', now) == 'c2corg_20261111083005'


def test_target_state_alias():
    client = _client(aliases={'c2corg': ['c2corg_b', 'c2corg_a']})
    assert im.get_target_state(client, 'c2corg') == (
        im.ALIAS,
        ['c2corg_a', 'c2corg_b'],
    )


def test_target_state_concrete_index():
    client = _client(indices=['c2corg'])
    assert im.get_target_state(client, 'c2corg') == (im.CONCRETE_INDEX, ['c2corg'])


def test_target_state_missing():
    assert im.get_target_state(_client(), 'c2corg') == (im.MISSING, [])


def test_serving_settings():
    client = MagicMock()
    client.indices.get_settings.return_value = {
        'c2corg_a': {
            'settings': {'index': {'refresh_interval': '5s', 'number_of_replicas': '0'}}
        }
    }
    assert im.get_serving_settings(client, ['c2corg_a']) == ('5s', 0)


def test_serving_settings_defaults():
    client = MagicMock()
    assert im.get_serving_settings(client, []) == ('1s', 1)
    client.indices.get_settings.return_value = {'i': {'settings': {'index': {}}}}
    assert im.get_serving_settings(client, ['i']) == ('1s', 1)


def test_switch_alias_is_atomic():
    client = MagicMock()
    im.switch_alias(client, 'c2corg', 'c2corg_new', im.ALIAS, ['c2corg_old'])
    client.indices.update_aliases.assert_called_once_with(
        body={
            'actions': [
                {'remove': {'index': 'c2corg_old', 'alias': 'c2corg'}},
                {'add': {'index': 'c2corg_new', 'alias': 'c2corg'}},
            ]
        }
    )
    client.indices.delete.assert_not_called()


def test_switch_alias_without_previous_index():
    client = MagicMock()
    im.switch_alias(client, 'c2corg', 'c2corg_new', im.MISSING, [])
    client.indices.update_aliases.assert_called_once_with(
        body={'actions': [{'add': {'index': 'c2corg_new', 'alias': 'c2corg'}}]}
    )


def test_switch_alias_replaces_concrete_index():
    client = MagicMock()
    im.switch_alias(client, 'c2corg', 'c2corg_new', im.CONCRETE_INDEX, ['c2corg'])
    client.indices.delete.assert_called_once_with(index='c2corg')
    client.indices.put_alias.assert_called_once_with(index='c2corg_new', name='c2corg')


def test_bulk_load_settings(monkeypatch):
    # the mappings are saved through the global connection, not the client
    monkeypatch.setattr(im, 'search_documents', {})
    client = MagicMock()
    im.create_index(client, 'c2corg_new', bulk_load=True)
    settings = client.indices.create.call_args.kwargs['body']['settings']
    assert settings['refresh_interval'] == '-1'
    assert settings['number_of_replicas'] == 0

    client.reset_mock()
    im.create_index(client, 'c2corg_new')
    settings = client.indices.create.call_args.kwargs['body']['settings']
    assert 'refresh_interval' not in settings
    assert 'number_of_replicas' not in settings


def test_finish_bulk_load():
    client = MagicMock()
    im.finish_bulk_load(client, 'c2corg_new', '1s', 1)
    client.indices.put_settings.assert_called_once_with(
        index='c2corg_new',
        body={'index': {'refresh_interval': '1s', 'number_of_replicas': 1}},
    )
    client.indices.refresh.assert_called_once_with(index='c2corg_new')
