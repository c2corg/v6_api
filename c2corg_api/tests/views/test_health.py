from c2corg_api.tests.views import BaseTestRest


class TestHealthRest(BaseTestRest):
    def setUp(self):
        super().setUp()

    def test_get(self):
        r = self.app.get('/health', status=200)

        data = r.json

        assert data['es'] == 'ok'
        assert data['redis'] == 'ok'

    def test_maintenance_mode(self, tmp_path, monkeypatch):
        # the load balancer probes HEAD /health and drains a server on 404
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'maintenance_mode.txt').touch()

        r = self.app.get('/health', status=404)
        assert r.json['maintenance_mode'] is True
        self.app.head('/health', status=404)

    def test_head(self):
        r = self.app.head('/health', status=200)
        assert r.body == b''
