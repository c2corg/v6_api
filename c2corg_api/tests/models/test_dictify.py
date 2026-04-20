"""Tests for c2corg_api.models.dictify — standalone dictify replacement."""

import json
import unittest

from c2corg_api.ext.geometry import wkbelement_from_geojson
from c2corg_api.models.dictify import _serialize_value, dictify
from c2corg_api.models.field_spec import FieldSpec


class TestFieldSpec:
    def test_to_dict(self):
        spec = FieldSpec(
            sa_model=None,
            columns=['id', 'username'],
            locale_fields=['lang', 'title'],
            geometry_fields=['version', 'geom'],
        )
        d = spec.to_dict()
        assert d['columns'] == ['id', 'username']
        assert d['locales'] == ['lang', 'title']
        assert d['geometry'] == ['version', 'geom']

    def test_to_dict_no_locales_or_geometry(self):
        spec = FieldSpec(sa_model=None, columns=['id'])
        d = spec.to_dict()
        assert d['columns'] == ['id']
        assert d['locales'] is None
        assert d['geometry'] is None

    def test_real_route_schema(self):
        """Ensure FieldSpec works with actual model schemas."""
        from c2corg_api.models.route import schema_route

        assert 'document_id' in schema_route.columns
        assert 'activities' in schema_route.columns
        assert schema_route.locale_fields is not None
        assert 'lang' in schema_route.locale_fields
        assert 'title' in schema_route.locale_fields
        assert schema_route.geometry_fields is not None
        assert 'geom' in schema_route.geometry_fields

    def test_real_listing_schema(self):
        """Listing schemas expose fewer columns."""
        from c2corg_api.models.area import schema_listing_area

        assert 'document_id' in schema_listing_area.columns
        assert 'area_type' in schema_listing_area.columns
        assert schema_listing_area.locale_fields is not None
        assert schema_listing_area.geometry_fields is None

    def test_real_user_schema(self):
        """User schema: no locales, no geometry."""
        from c2corg_api.models.user import schema_user

        assert 'id' in schema_user.columns
        assert 'username' in schema_user.columns
        assert schema_user.locale_fields is None
        assert schema_user.geometry_fields is None

    def test_restrict(self):
        spec = FieldSpec(
            sa_model=None,
            columns=['document_id', 'version', 'quality', 'area_type'],
            locale_fields=['version', 'lang', 'title', 'description'],
            geometry_fields=['version', 'geom', 'geom_detail'],
        )
        restricted = spec.restrict(['area_type', 'locales.title', 'geometry.geom'])
        assert 'document_id' in restricted.columns  # default
        assert 'version' in restricted.columns  # default
        assert 'area_type' in restricted.columns
        assert 'quality' not in restricted.columns

        assert 'lang' in restricted.locale_fields  # default
        assert 'title' in restricted.locale_fields
        assert 'description' not in restricted.locale_fields

        assert 'version' in restricted.geometry_fields  # default
        assert 'geom' in restricted.geometry_fields
        assert 'geom_detail' not in restricted.geometry_fields


class _FakeObj:
    """Lightweight mock for a SQLAlchemy model instance."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestDictify:
    def test_flat_columns(self):
        obj = _FakeObj(id=42, username='alice', email='a@b.com')
        spec = {
            'columns': ['id', 'username', 'email'],
            'locales': None,
            'geometry': None,
        }
        result = dictify(obj, spec)
        assert result == {'id': 42, 'username': 'alice', 'email': 'a@b.com'}

    def test_none_values_preserved(self):
        obj = _FakeObj(id=1, name=None)
        spec = {'columns': ['id', 'name'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        assert result == {'id': 1, 'name': None}

    def test_datetime_serialized(self):
        from datetime import datetime

        dt = datetime(2025, 6, 15, 12, 30, 0)
        obj = _FakeObj(created=dt)
        spec = {'columns': ['created'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        assert result['created'] == '2025-06-15T12:30:00'

    def test_wkbelement_serialized(self):
        wkb_elem = wkbelement_from_geojson(
            {'type': 'Point', 'coordinates': [6.0, 45.0]}, 3857
        )
        obj = _FakeObj(geom=wkb_elem)
        spec = {'columns': ['geom'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        # Result should be a GeoJSON string
        parsed = json.loads(result['geom'])
        assert parsed['type'] == 'Point'

    def test_with_locales(self):
        locale_fr = _FakeObj(lang='fr', title='Bonjour')
        locale_en = _FakeObj(lang='en', title='Hello')
        obj = _FakeObj(document_id=1, locales=[locale_fr, locale_en])
        spec = {
            'columns': ['document_id'],
            'locales': ['lang', 'title'],
            'geometry': None,
        }
        result = dictify(obj, spec)
        assert result['document_id'] == 1
        assert len(result['locales']) == 2
        assert result['locales'][0] == {'lang': 'fr', 'title': 'Bonjour'}
        assert result['locales'][1] == {'lang': 'en', 'title': 'Hello'}

    def test_with_geometry(self):
        wkb_elem = wkbelement_from_geojson(
            {'type': 'Point', 'coordinates': [6.0, 45.0]}, 3857
        )
        geom = _FakeObj(version=1, geom=wkb_elem)
        obj = _FakeObj(document_id=1, geometry=geom)
        spec = {
            'columns': ['document_id'],
            'locales': None,
            'geometry': ['version', 'geom'],
        }
        result = dictify(obj, spec)
        assert result['document_id'] == 1
        assert result['geometry'] is not None
        assert result['geometry']['version'] == 1
        parsed = json.loads(result['geometry']['geom'])
        assert parsed['type'] == 'Point'

    def test_geometry_none(self):
        obj = _FakeObj(document_id=1, geometry=None)
        spec = {
            'columns': ['document_id'],
            'locales': None,
            'geometry': ['version', 'geom'],
        }
        result = dictify(obj, spec)
        assert result['geometry'] is None

    def test_list_column(self):
        """Array columns (e.g. activities) should be preserved as lists."""
        obj = _FakeObj(activities=['skitouring', 'hiking'])
        spec = {'columns': ['activities'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        assert result['activities'] == ['skitouring', 'hiking']


class TestSerializeValue:
    def test_none(self):
        assert _serialize_value(None) is None

    def test_string(self):
        assert _serialize_value('hello') == 'hello'

    def test_int(self):
        assert _serialize_value(42) == 42

    def test_float(self):
        assert _serialize_value(3.14) == 3.14

    def test_bool(self):
        assert _serialize_value(True) is True

    def test_list(self):
        assert _serialize_value([1, 'a']) == [1, 'a']


if __name__ == '__main__':
    unittest.main()
