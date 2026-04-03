"""Tests for c2corg_api.models.dictify — standalone dictify replacement."""
import json
import unittest

from c2corg_api.models.dictify import dictify, fields_from_schema, \
    _serialize_value

from c2corg_api.ext.colander_ext import wkbelement_from_geojson


class _FakeChild:
    """Minimal stand-in for a colander SchemaNode child."""
    def __init__(self, name):
        self.name = name
        self.children = []

    def __iter__(self):
        return iter(self.children)


class _FakeInspector:
    """Minimal stand-in for the mapper-like inspector on a schema."""
    class _Rels:
        locales = True
        geometry = True

    class _NoAttr:
        pass

    def __init__(self, rel_names):
        self._rel_names = rel_names

    @property
    def relationships(self):
        return type('R', (), {
            '__getattr__': lambda self_, name:
                True if name in self._rel_names
                else (_ for _ in ()).throw(AttributeError(name))
        })()

    @property
    def column_attrs(self):
        return self._NoAttr()


class _FakeSchema:
    """Minimal stand-in for a SQLAlchemySchemaNode."""
    def __init__(self, children, rel_names=None):
        self._children = children
        self.inspector = _FakeInspector(rel_names or set())

    def __iter__(self):
        return iter(self._children)


class TestFieldsFromSchema(unittest.TestCase):

    def test_columns_only(self):
        children = [
            _FakeChild('id'),
            _FakeChild('username'),
            _FakeChild('email')
        ]
        schema = _FakeSchema(children)
        spec = fields_from_schema(schema)
        self.assertEqual(spec['columns'], ['id', 'username', 'email'])
        self.assertIsNone(spec['locales'])
        self.assertIsNone(spec['geometry'])

    def test_with_locales_and_geometry(self):
        locales_child = _FakeChild('locales')
        locale_inner = _FakeChild('')
        locale_inner.children = [_FakeChild('lang'), _FakeChild('title')]
        locales_child.children = [locale_inner]

        geom_child = _FakeChild('geometry')
        geom_child.children = [_FakeChild('version'), _FakeChild('geom')]

        children = [
            _FakeChild('document_id'),
            locales_child,
            geom_child,
            _FakeChild('quality'),
        ]
        schema = _FakeSchema(children, rel_names={'locales', 'geometry'})
        spec = fields_from_schema(schema)
        self.assertEqual(spec['columns'], ['document_id', 'quality'])
        self.assertEqual(spec['locales'], ['lang', 'title'])
        self.assertEqual(spec['geometry'], ['version', 'geom'])

    def test_real_schema(self):
        """Ensure extraction works with actual ColanderAlchemy schemas."""
        from c2corg_api.models.route import schema_route
        spec = fields_from_schema(schema_route)
        self.assertIn('document_id', spec['columns'])
        self.assertIn('activities', spec['columns'])
        self.assertIsNotNone(spec['locales'])
        self.assertIn('lang', spec['locales'])
        self.assertIn('title', spec['locales'])
        self.assertIsNotNone(spec['geometry'])
        self.assertIn('geom', spec['geometry'])

    def test_real_listing_schema(self):
        """Listing schemas expose fewer columns."""
        from c2corg_api.models.area import schema_listing_area
        spec = fields_from_schema(schema_listing_area)
        self.assertIn('document_id', spec['columns'])
        self.assertIn('area_type', spec['columns'])
        # Listing area has locales but no geometry
        self.assertIsNotNone(spec['locales'])
        self.assertIsNone(spec['geometry'])

    def test_real_user_schema(self):
        """User schema: no locales, no geometry."""
        from c2corg_api.models.user import schema_user
        spec = fields_from_schema(schema_user)
        self.assertIn('id', spec['columns'])
        self.assertIn('username', spec['columns'])
        self.assertIsNone(spec['locales'])
        self.assertIsNone(spec['geometry'])


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
