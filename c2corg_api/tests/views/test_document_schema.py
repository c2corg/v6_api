from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document_schemas import route_documents_config, \
    topo_map_documents_config


class TestGetDocumentsConfig(BaseTestRest):

    def test_get_load_only_fields_routes(self):
        fields = route_documents_config.get_load_only_fields()
        self.assertIn('elevation_max', fields)
        self.assertIn('ski_rating', fields)
        self.assertIn('rock_free_rating', fields)
        self.assertNotIn('height_diff_access', fields)
        self.assertNotIn('lift_access', fields)

        self.assertNotIn('geometry.geom', fields)
        self.assertNotIn('geom', fields)

        self.assertNotIn('locales.title', fields)
        self.assertNotIn('title', fields)

    def test_get_load_only_fields_locales_routes(self):
        fields = route_documents_config.get_load_only_fields_locales()
        self.assertIn('title', fields)
        self.assertIn('title_prefix', fields)
        self.assertIn('summary', fields)
        self.assertNotIn('description', fields)
        self.assertNotIn('gear', fields)

    def test_get_load_only_fields_geometry_routes(self):
        fields = route_documents_config.get_load_only_fields_geometry()
        self.assertIn('geom', fields)
        self.assertNotIn('geom_detail', fields)

    def test_get_load_only_fields_topo_map(self):
        fields = topo_map_documents_config.get_load_only_fields()
        self.assertIn('code', fields)
        self.assertIn('editor', fields)
        self.assertNotIn('scale', fields)
        self.assertNotIn('lift_access', fields)

    def test_get_load_only_fields_locales_topo_map(self):
        fields = topo_map_documents_config.get_load_only_fields_locales()
        self.assertIn('title', fields)
        self.assertNotIn('summary', fields)
        self.assertNotIn('description', fields)

    def test_get_load_only_fields_geometry_topo_map(self):
        fields = topo_map_documents_config.get_load_only_fields_geometry()
        self.assertNotIn('geom', fields)
        self.assertNotIn('geom_detail', fields)
