import pytest


class TestHealthRest:
    @pytest.fixture(autouse=True)
    def _setup_test_health_rest(self, client):
        pass

    def test_get(self, client):
        r = client.get('/health', status=200)

        data = r.json

        assert data['es'] == 'ok'
        assert data['redis'] == 'ok'

    def test_maintenance_mode(self, tmp_path, monkeypatch, client):
        # the load balancer probes HEAD /health and drains a server on 404
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'maintenance_mode.txt').touch()

        r = client.get('/health', status=404)
        assert r.json['maintenance_mode'] is True
        client.head('/health', status=404)

    def test_head(self, client):
        r = client.head('/health', status=200)
        assert r.body == b''
