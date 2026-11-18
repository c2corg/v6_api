def test_get(client):
    r = client.get('/health', status=200)

    data = r.json

    assert data['es'] == 'ok'
    assert data['redis'] == 'ok'


def test_maintenance_mode(tmp_path, monkeypatch, client):
    # the load balancer probes HEAD /health and drains a server on 404
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'maintenance_mode.txt').touch()

    r = client.get('/health', status=404)
    assert r.json['maintenance_mode'] is True
    client.head('/health', status=404)


def test_head(client):
    r = client.head('/health', status=200)
    assert r.body == b''


def test_es_alias(monkeypatch, client):
    # after reindex_es the configured name is an alias: the stats are keyed by
    # the real index (c2corg_<timestamp>), the health check must still pass
    from c2corg_api.search import elasticsearch_config

    class Indices:
        def stats(self, index, metric=None):
            return {
                '_all': {'total': {'docs': {'count': 42}}},
                'indices': {index + '_20261118': {'total': {'docs': {'count': 42}}}},
            }

    class Client:
        indices = Indices()

    monkeypatch.setitem(elasticsearch_config, 'client', Client())

    r = client.get('/health', status=200)
    assert r.json['es'] == 'ok'
    assert r.json['es_indexed_docs'] == 42
