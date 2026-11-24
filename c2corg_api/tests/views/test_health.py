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


def test_partners_status_empty(client):
    # no source ever ran: still a 200
    r = client.get('/health', status=200)
    assert r.json['partners'] == {}


def test_partners_status(client, session):
    from c2corg_api.models import DBSession
    from c2corg_api.models.partner_outing import PartnerSource

    DBSession.add(PartnerSource(source='skitour', status='disabled'))
    DBSession.add(PartnerSource(source='gulliver', status='blocked'))
    DBSession.flush()

    r = client.get('/health', status=200)
    assert r.json['partners'] == {'skitour': 'disabled', 'gulliver': 'blocked'}


def test_partners_status_failure_does_not_fail_the_check(client, monkeypatch):
    from c2corg_api.web import health

    # the query raises: the key is empty and the status stays 200
    monkeypatch.setattr(health, 'PartnerSource', None)
    r = client.get('/health', status=200)
    assert r.json['partners'] == {}
