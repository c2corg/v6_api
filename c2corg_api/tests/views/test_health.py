def test_get(client):
    r = client.get('/health', status=200)

    data = r.json

    assert data['es'] == 'ok'
    assert data['redis'] == 'ok'
    # no CI Docker build arguments in the tests: present but empty
    assert data['version']
    assert data['describe'] == ''
    assert data['commit_date'] == ''


def test_describe(monkeypatch, fastapi_app, client):
    # given by the CI Docker build (common.ini.in), next to the version
    settings = fastapi_app.state.settings
    monkeypatch.setitem(settings, 'version.describe', 'v6.45.0-12-gabc1234')
    monkeypatch.setitem(settings, 'version.commit_date', '2026-11-20T10:02:03+01:00')

    r = client.get('/health', status=200)
    assert r.json['describe'] == 'v6.45.0-12-gabc1234'
    assert r.json['commit_date'] == '2026-11-20T10:02:03+01:00'
    assert r.json['version'] == settings['cache_version']


def test_describe_missing(monkeypatch, fastapi_app, client):
    # a common.ini generated before these settings existed: empty, no error
    settings = fastapi_app.state.settings
    monkeypatch.delitem(settings, 'version.describe', raising=False)
    monkeypatch.delitem(settings, 'version.commit_date', raising=False)

    r = client.get('/health', status=200)
    assert r.json['describe'] == ''
    assert r.json['commit_date'] == ''


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


def test_es_down(monkeypatch, client):
    # the documents are still served without ES: the health check passes (the
    # load balancer keeps the server) and a search answers 503
    from elasticsearch import Elasticsearch

    from c2corg_api.search import elasticsearch_config

    unreachable = Elasticsearch(['localhost:1'], max_retries=0, timeout=1)
    monkeypatch.setitem(elasticsearch_config, 'client', unreachable)

    r = client.get('/health', status=200)
    assert r.json['es'] == 'error'
    assert r.json['es_indexed_docs'] is None

    r = client.get('/outings?act=skitouring', status=503)
    assert r.json['errors'][0]['name'] == 'search unavailable'


def test_partners_in_the_harvest_status(client, session):
    # the partner sources are harvest sources: one representation for all
    from datetime import UTC, datetime

    from c2corg_api.models import DBSession
    from c2corg_api.models.harvest import HarvestSource

    now = datetime(2026, 11, 25, 10, tzinfo=UTC)
    DBSession.add(
        HarvestSource(
            id='partners.skitour:outings',
            harvester='partners.skitour',
            next_run_at=now,
            last_success=now,
        )
    )
    DBSession.add(
        HarvestSource(
            id='partners.gulliver:outings',
            harvester='partners.gulliver',
            next_run_at=now,
            error_count=2,
        )
    )
    DBSession.flush()

    r = client.get('/health', status=200)
    assert r.json['harvest']['partners.skitour'] == {
        'sources': 1,
        'failing': 0,
        'last_success': '2026-11-25T10:00:00+00:00',
    }
    assert r.json['harvest']['partners.gulliver']['failing'] == 1
    assert 'partners' not in r.json
