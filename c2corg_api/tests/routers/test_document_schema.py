"""
Tests for ``GetDocumentsConfig`` field configurations used by FastAPI routers.

Mirrors ``c2corg_api/tests/views/test_document_schema.py``.
The routers still rely on ``document_schemas`` for collection queries
(``load_only`` field lists), so these tests remain relevant.
"""

from c2corg_api.tests import BaseTestCase
from c2corg_api.views.document_schemas import (
    route_documents_config,
    topo_map_documents_config,
)


class TestGetDocumentsConfig(BaseTestCase):
    """Unit tests for the ``GetDocumentsConfig`` load-only field helpers."""

    @staticmethod
    def _field_names(fields):
        return [f.key for f in fields]

    def test_get_load_only_fields_routes(self):
        fields = self._field_names(route_documents_config.get_load_only_fields())
        assert 'elevation_max' in fields
        assert 'ski_rating' in fields
        assert 'rock_free_rating' in fields
        assert 'height_diff_access' not in fields
        assert 'lift_access' not in fields

        assert 'geometry.geom' not in fields
        assert 'geom' not in fields

        assert 'locales.title' not in fields
        assert 'title' not in fields

    def test_get_load_only_fields_locales_routes(self):
        fields = self._field_names(
            route_documents_config.get_load_only_fields_locales()
        )
        assert 'title' in fields
        assert 'title_prefix' in fields
        assert 'summary' in fields
        assert 'description' not in fields
        assert 'gear' not in fields

    def test_get_load_only_fields_geometry_routes(self):
        fields = self._field_names(
            route_documents_config.get_load_only_fields_geometry()
        )
        assert 'geom' in fields
        assert 'geom_detail' not in fields

    def test_get_load_only_fields_topo_map(self):
        fields = self._field_names(topo_map_documents_config.get_load_only_fields())
        assert 'code' in fields
        assert 'editor' in fields
        assert 'scale' not in fields
        assert 'lift_access' not in fields

    def test_get_load_only_fields_locales_topo_map(self):
        fields = self._field_names(
            topo_map_documents_config.get_load_only_fields_locales()
        )
        assert 'title' in fields
        assert 'summary' not in fields
        assert 'description' not in fields

    def test_get_load_only_fields_geometry_topo_map(self):
        fields = self._field_names(
            topo_map_documents_config.get_load_only_fields_geometry()
        )
        assert 'geom' not in fields
        assert 'geom_detail' not in fields
