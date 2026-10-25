from c2corg_api.models.coverage import Coverage
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.tests.views import BaseTestRest

POLYGON = (
    '{"type": "Polygon", "coordinates": [[[635000, 5723000], [635000, 5724000], '
    '[637000, 5724000], [637000, 5723000], [635000, 5723000]]]}'
)


class TestCoverageRest(BaseTestRest):
    def setUp(self):
        self.headers = self.add_authorization_header(username='contributor')
        body = {
            'coverage_type': 'fr-se',
            'geometry': {'geom_detail': POLYGON},
            'locales': [{'lang': 'en', 'title': 'South-East'}],
        }
        response = self.app_post_json('/coverages', body, headers=self.headers)
        self.document_id = response.json['document_id']

    def _put(self, change):
        document = self.app.get(f'/coverages/{self.document_id}').json
        change(document)
        body = {'message': 'update', 'document': document}
        self.app_put_json(
            f'/coverages/{self.document_id}', body, headers=self.headers, status=200
        )
        self.session.expire_all()
        return self.session.get(Coverage, self.document_id)

    def _versions(self):
        return (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.document_id)
            .count()
        )

    def test_update_locale_only(self):
        # coverages have no history: an update used to look for the previous
        # archive and answer 500
        def change(document):
            document['locales'][0]['title'] = 'Sud-Est'

        coverage = self._put(change)
        assert coverage.get_locale('en').title == 'Sud-Est'
        assert self._versions() == 0

    def test_update_figures(self):
        def change(document):
            document['coverage_type'] = 'fr-ne'

        coverage = self._put(change)
        assert coverage.coverage_type == 'fr-ne'
        assert self._versions() == 0
