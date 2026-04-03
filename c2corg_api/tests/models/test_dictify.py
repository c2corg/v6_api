"""Tests for c2corg_api.models.dictify — standalone dictify replacement."""
import json
import unittest

from c2corg_api.models.dictify import dictify, _serialize_value
from c2corg_api.models.field_spec import FieldSpec

from c2corg_api.ext.geometry import wkbelement_from_geojson


class TestFieldSpec(unittest.TestCase):

    def test_to_dict(self):
        spec = FieldSpec(
            sa_model=None,
            columns=['id', 'username'],
            locale_fields=['lang', 'title'],
            geometry_fields=['version', 'geom'],
        )
        d = spec.to_dict()
        self.assertEqual(d['columns'], ['id', 'username'])
        self.assertEqual(d['locales'], ['lang', 'title'])
        self.assertEqual(d['geometry'], ['version', 'geom'])

    def test_to_dict_no_locales_or_geometry(self):
        spec = FieldSpec(sa_model=None, columns=['id'])
        d = spec.to_dict()
        self.assertEqual(d['columns'], ['id'])
        self.assertIsNone(d['locales'])
        self.assertIsNone(d['geometry'])

    def test_real_route_schema(self):
        """Ensure FieldSpec works with actual model schemas."""
        from c2corg_api.models.route import schema_route
        self.assertIn('document_id', schema_route.columns)
        self.assertIn('activities', schema_route.columns)
        self.assertIsNotNone(schema_route.locale_fields)
        self.assertIn('lang', schema_route.locale_fields)
        self.assertIn('title', schema_route.locale_fields)
        self.assertIsNotNone(schema_route.geometry_fields)
        self.assertIn('geom', schema_route.geometry_fields)

    def test_real_listing_schema(self):
        """Listing schemas expose fewer columns."""
        from c2corg_api.models.area import schema_listing_area
        self.assertIn('document_id', schema_listing_area.columns)
        self.assertIn('area_type', schema_listing_area.columns)
        self.assertIsNotNone(schema_listing_area.locale_fields)
        self.assertIsNone(schema_listing_area.geometry_fields)

    def test_real_user_schema(self):
        """User schema: no locales, no geometry."""
        from c2corg_api.models.user import schema_user
        self.assertIn('id', schema_user.columns)
        self.assertIn('username', schema_user.columns)
        self.assertIsNone(schema_user.locale_fields)
        self.assertIsNone(schema_user.geometry_fields)

    def test_restrict(self):
        spec = FieldSpec(
            sa_model=None,
            columns=['document_id', 'version', 'quality', 'area_type'],
            locale_fields=['version', 'lang', 'title', 'description'],
            geometry_fields=['version', 'geom', 'geom_detail'],
        )
        restricted = spec.restrict([
            'area_type', 'locales.title', 'geometry.geom',
        ])
        self.assertIn('document_id', restricted.columns)  # default
        self.assertIn('version', restricted.columns)       # default
        self.assertIn('area_type', restricted.columns)
        self.assertNotIn('quality', restricted.columns)

        self.assertIn('lang', restricted.locale_fields)    # default
        self.assertIn('title', restricted.locale_fields)
        self.assertNotIn('description', restricted.locale_fields)

        self.assertIn('version', restricted.geometry_fields)  # default
        self.assertIn('geom', restricted.geometry_fields)
        self.assertNotIn('geom_detail', restricted.geometry_fields)


class _FakeObj:
    """Lightweight mock for a SQLAlchemy model instance."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestDictify(unittest.TestCase):

    def test_flat_columns(self):
        obj = _FakeObj(id=42, username='alice', email='a@b.com')
        spec = {'columns': ['id', 'username', 'email'],
                'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        self.assertEqual(result, {
            'id': 42, 'username': 'alice', 'email': 'a@b.com'
        })

    def test_none_values_preserved(self):
        obj = _FakeObj(id=1, name=None)
        spec = {'columns': ['id', 'name'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        self.assertEqual(result, {'id': 1, 'name': None})

    def test_datetime_serialized(self):
        import datetime
        dt = datetime.datetime(2025, 6, 15, 12, 30, 0)
        obj = _FakeObj(created=dt)
        spec = {'columns': ['created'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        self.assertEqual(result['created'], '2025-06-15T12:30:00')

    def test_wkbelement_serialized(self):
        wkb_elem = wkbelement_from_geojson(
            {"type": "Point", "coordinates": [6.0, 45.0]}, 3857)
        obj = _FakeObj(geom=wkb_elem)
        spec = {'columns': ['geom'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        # Result should be a GeoJSON string
        parsed = json.loads(result['geom'])
        self.assertEqual(parsed['type'], 'Point')

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
        self.assertEqual(result['document_id'], 1)
        self.assertEqual(len(result['locales']), 2)
        self.assertEqual(result['locales'][0],
                         {'lang': 'fr', 'title': 'Bonjour'})
        self.assertEqual(result['locales'][1],
                         {'lang': 'en', 'title': 'Hello'})

    def test_with_geometry(self):
        wkb_elem = wkbelement_from_geojson(
            {"type": "Point", "coordinates": [6.0, 45.0]}, 3857)
        geom = _FakeObj(version=1, geom=wkb_elem)
        obj = _FakeObj(document_id=1, geometry=geom)
        spec = {
            'columns': ['document_id'],
            'locales': None,
            'geometry': ['version', 'geom'],
        }
        result = dictify(obj, spec)
        self.assertEqual(result['document_id'], 1)
        self.assertIsNotNone(result['geometry'])
        self.assertEqual(result['geometry']['version'], 1)
        parsed = json.loads(result['geometry']['geom'])
        self.assertEqual(parsed['type'], 'Point')

    def test_geometry_none(self):
        obj = _FakeObj(document_id=1, geometry=None)
        spec = {
            'columns': ['document_id'],
            'locales': None,
            'geometry': ['version', 'geom'],
        }
        result = dictify(obj, spec)
        self.assertIsNone(result['geometry'])

    def test_list_column(self):
        """Array columns (e.g. activities) should be preserved as lists."""
        obj = _FakeObj(activities=['skitouring', 'hiking'])
        spec = {'columns': ['activities'], 'locales': None, 'geometry': None}
        result = dictify(obj, spec)
        self.assertEqual(result['activities'], ['skitouring', 'hiking'])


class TestSerializeValue(unittest.TestCase):

    def test_none(self):
        self.assertIsNone(_serialize_value(None))

    def test_string(self):
        self.assertEqual(_serialize_value('hello'), 'hello')

    def test_int(self):
        self.assertEqual(_serialize_value(42), 42)

    def test_float(self):
        self.assertEqual(_serialize_value(3.14), 3.14)

    def test_bool(self):
        self.assertIs(_serialize_value(True), True)

    def test_list(self):
        self.assertEqual(_serialize_value([1, 'a']), [1, 'a'])


if __name__ == '__main__':
    unittest.main()
