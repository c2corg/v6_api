from c2corg_api.models.stoparea import Stoparea
from c2corg_api.tests.views import BaseDocumentTestRest


class TestStopareaRest(BaseDocumentTestRest):
    def setUp(self):
        self.set_prefix_and_model('/stopareas', 'sa', Stoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        # Create a stoparea for testing
        stoparea = Stoparea(
            stoparea_id=1,
            navitia_id='nav1',
            stoparea_name='Stop Area 1',
            line='line1',
            operator='operator1',
        )

        self.session.add(stoparea)
        self.session.flush()

    def test_collection_get(self):
        """Test getting list of stopareas."""
        response = self.app.get('/stopareas', status=200)
        result = response.json

        assert result['total_results'] >= 0
        assert isinstance(result['documents'], list)

    def test_collection_get_page(self):
        self.session.add(
            Stoparea(
                stoparea_id=2,
                navitia_id='nav2',
                stoparea_name='Stop Area 2',
                line='line2',
                operator='operator2',
            )
        )
        self.session.flush()
        response = self.app.get('/stopareas?page_id=2&nb_items=1', status=200)
        result = response.json

        assert result['total_results'] == 2
        assert len(result['documents']) == 1

    def test_collection_get_invalid_page(self):
        response = self.app.get('/stopareas?page_id=0&nb_items=x', status=400)
        names = [e['name'] for e in response.json['errors']]

        assert names == ['page_id', 'nb_items']

    def test_get_stoparea_not_found(self):
        """Test getting a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/999999', status=404)
        result = response.json

        assert result['error'] == 'Stoparea not found'

    def test_get_stoparea_found(self):
        """Test getting a stoparea that exists."""
        response = self.app.get('/stopareas/1', status=200)
        result = response.json

        assert result['id'] == 1
        assert result['navitia_id'] == 'nav1'
        assert result['stoparea_name'] == 'Stop Area 1'
        assert result['line'] == 'line1'
        assert result['operator'] == 'operator1'


class TestStopareaInfoRest(BaseDocumentTestRest):
    def setUp(self):
        self.set_prefix_and_model('/stopareas', 'sa', Stoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        # Create a stoparea for testing
        stoparea = Stoparea(
            stoparea_id=1,
            navitia_id='nav1',
            stoparea_name='Stop Area 1',
            line='line1',
            operator='operator1',
        )

        self.session.add(stoparea)
        self.session.flush()

    def test_get_info_stoparea_not_found(self):
        """Test getting info for a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/999999/fr/info', status=404)
        result = response.json

        assert result['error'] == 'Stoparea not found'

    def test_get_info_stoparea_found(self):
        """Test getting info for a stoparea that exists."""
        response = self.app.get('/stopareas/1/fr/info', status=200)
        result = response.json

        assert result['stoparea_id'] == 1
        assert result['attributes']['navitia_id'] == 'nav1'
        assert result['attributes']['stoparea_name'] == 'Stop Area 1'
        assert result['attributes']['line'] == 'line1'
        assert result['attributes']['operator'] == 'operator1'

    def test_get_info_stoparea_lang_not_found(self):
        """Test getting info for a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/1/invalid/info', status=400)
        result = response.json

        assert result['errors'][0]['description'] == 'invalid lang'
