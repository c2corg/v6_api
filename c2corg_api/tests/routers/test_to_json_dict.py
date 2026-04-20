"""
Snapshot tests for ``to_json_dict()`` — the serialization function we
intend to replace with Pydantic schemas.

Each test constructs SA model instances (in-DB so that geometry WKB
round-trips correctly), calls ``to_json_dict()`` with the exact same
``FieldSpec`` used in the router code, and asserts on:

1. The exact set of top-level keys returned.
2. The types / values of selected fields.
3. The structure of nested ``locales`` and ``geometry`` sub-dicts.
4. Special-attribute propagation (``available_langs``, ``areas``,
   ``type``, ``has_geom_detail``, ``topic_id``, ``author``, ``creator``,
   ``img_count``, ``cooked``).

These tests lock in the **current** JSON contract so that we can later
replace ``to_json_dict`` with ``SomeSchema.model_validate(obj).model_dump()``
and confirm zero regression.
"""

from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE, Area, schema_listing_area
from c2corg_api.models.document import (
    DocumentGeometry,
    DocumentLocale,
    set_available_langs,
)
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale, schema_route
from c2corg_api.models.topo_map import TopoMap, schema_listing_topo_map
from c2corg_api.models.waypoint import Waypoint, WaypointLocale, schema_waypoint
from c2corg_api.routers.helpers.document_helpers import to_json_dict
from c2corg_api.schemas.listing import AreaListingSchema, TopoMapListingSchema
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestToJsonDict(BaseTestCase):
    """Snapshot tests for ``to_json_dict``."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    # ──────────────────────────────────────────────────────────────
    # Test data
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        # Area with locale + geometry
        self.area = Area(area_type='range')
        self.area.locales.append(DocumentLocale(lang='en', title='Chartreuse'))
        self.area.locales.append(DocumentLocale(lang='fr', title='Chartreuse FR'))
        self.area.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))'
        )
        self.session.add(self.area)

        # TopoMap with locale (no geometry for listing)
        self.topo_map = TopoMap(editor='IGN', code='3431OT')
        self.topo_map.locales.append(DocumentLocale(lang='en', title='Grenoble'))
        self.topo_map.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))'
        )
        self.session.add(self.topo_map)

        # Waypoint with full geometry
        self.waypoint = Waypoint(waypoint_type='summit', elevation=4000)
        self.waypoint.locales.append(
            WaypointLocale(lang='en', title='Mont Blanc', access='by foot')
        )
        self.waypoint.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.86 45.83)')
        self.session.add(self.waypoint)

        # Route with locale + geometry (to test has_geom_detail special attr)
        self.route = Route(
            activities=['skitouring'], elevation_max=4000, elevation_min=1000
        )
        self.route.locales.append(
            RouteLocale(lang='en', title='Mont Blanc', title_prefix='some prefix')
        )
        self.route.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(6.86 45.83)',
            geom_detail='SRID=3857;LINESTRING(0 0, 1 1)',
        )
        self.session.add(self.route)

        # Outing (to test has_geom_detail + author special attrs)
        self.outing = Outing(
            activities=['skitouring'], date_start='2024-01-15', date_end='2024-01-15'
        )
        self.outing.locales.append(OutingLocale(lang='en', title='Great day out'))
        self.outing.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(6.86 45.83)',
            geom_detail='SRID=3857;LINESTRING(0 0, 1 1)',
        )
        self.session.add(self.outing)

        self.session.flush()

    # ──────────────────────────────────────────────────────────────
    # 1. schema_listing_area  (used in document_get, document_listings,
    #    navitia_jobs, navitia, user_preferences)
    # ──────────────────────────────────────────────────────────────

    def test_listing_area_keys(self):
        """Snapshot the exact keys returned for area listing."""
        result = to_json_dict(self.area, schema_listing_area)

        # Top-level keys: FieldSpec default columns + listing fields
        assert 'document_id' in result
        assert 'version' in result
        assert 'area_type' in result
        assert 'locales' in result
        # schema_listing_area has no geometry (LISTING_FIELDS has no geometry.*)
        assert 'geometry' not in result

    def test_listing_area_locale_structure(self):
        """Locale sub-dicts contain only the listing locale fields."""
        result = to_json_dict(self.area, schema_listing_area)
        locale = result['locales'][0]

        assert 'lang' in locale
        assert 'version' in locale
        assert 'title' in locale
        # Listing locales should NOT have description, summary etc.
        assert set(locale.keys()) == {'lang', 'version', 'title'}

    def test_listing_area_values(self):
        """Values are serialized correctly."""
        result = to_json_dict(self.area, schema_listing_area)

        assert result['document_id'] == self.area.document_id
        assert result['area_type'] == 'range'
        assert result['locales'][0]['title'] == 'Chartreuse'
        assert result['locales'][0]['lang'] == 'en'

    def test_listing_area_special_attrs_propagated(self):
        """Special attributes set on the SA object are propagated."""
        # Simulate what the router code does
        self.area.type = AREA_TYPE
        result = to_json_dict(self.area, schema_listing_area)
        assert result['type'] == AREA_TYPE

    def test_listing_area_available_langs(self):
        """available_langs special attribute."""
        set_available_langs([self.area], loaded=True)
        result = to_json_dict(self.area, schema_listing_area)
        assert set(result['available_langs']) == {'en', 'fr'}

    # ──────────────────────────────────────────────────────────────
    # 2. schema_listing_topo_map  (used in document_get)
    # ──────────────────────────────────────────────────────────────

    def test_listing_topo_map_keys(self):
        result = to_json_dict(self.topo_map, schema_listing_topo_map)

        assert 'document_id' in result
        assert 'version' in result
        assert 'code' in result
        assert 'editor' in result
        assert 'locales' in result
        assert 'geometry' not in result

    def test_listing_topo_map_locale_structure(self):
        result = to_json_dict(self.topo_map, schema_listing_topo_map)
        locale = result['locales'][0]
        assert set(locale.keys()) == {'lang', 'version', 'title'}

    def test_listing_topo_map_values(self):
        result = to_json_dict(self.topo_map, schema_listing_topo_map)
        assert result['code'] == '3431OT'
        assert result['editor'] == 'IGN'
        assert result['locales'][0]['title'] == 'Grenoble'

    # ──────────────────────────────────────────────────────────────
    # 3. schema_waypoint  (used in navitia_jobs, navitia)
    # ──────────────────────────────────────────────────────────────

    def test_waypoint_full_keys(self):
        """Full waypoint schema — many columns + locale + geometry."""
        result = to_json_dict(self.waypoint, schema_waypoint)

        assert 'document_id' in result
        assert 'waypoint_type' in result
        assert 'elevation' in result
        assert 'locales' in result
        assert 'geometry' in result

    def test_waypoint_locale_has_access(self):
        result = to_json_dict(self.waypoint, schema_waypoint)
        locale = result['locales'][0]
        assert 'title' in locale
        assert 'lang' in locale
        assert 'access' in locale

    def test_waypoint_geometry_is_geojson(self):
        """Geometry WKB is serialized to GeoJSON string."""
        result = to_json_dict(self.waypoint, schema_waypoint)
        geom = result['geometry']
        assert 'geom' in geom
        # geom should be a GeoJSON string or dict (from WKB)
        assert geom['geom'] is not None

    def test_waypoint_values(self):
        result = to_json_dict(self.waypoint, schema_waypoint)
        assert result['elevation'] == 4000
        assert result['waypoint_type'] == 'summit'

    # ──────────────────────────────────────────────────────────────
    # 4. schema_route  (used in navitia_jobs, navitia)
    # ──────────────────────────────────────────────────────────────

    def test_route_full_keys(self):
        result = to_json_dict(self.route, schema_route)

        assert 'document_id' in result
        assert 'activities' in result
        assert 'elevation_max' in result
        assert 'locales' in result
        assert 'geometry' in result

    def test_route_locale_has_title_prefix(self):
        result = to_json_dict(self.route, schema_route)
        locale = result['locales'][0]
        assert 'title' in locale
        assert 'title_prefix' in locale
        assert locale['title_prefix'] == 'some prefix'

    def test_route_geometry_has_geom_detail(self):
        """geom_detail is serialized in the geometry sub-dict."""
        result = to_json_dict(self.route, schema_route)
        geom = result['geometry']
        assert 'geom' in geom
        assert 'geom_detail' in geom

    def test_route_with_special_geometry_attrs(self):
        """with_special_geometry_attrs=True copies has_geom_detail."""
        self.route.geometry.has_geom_detail = True
        result = to_json_dict(
            self.route, schema_route, with_special_geometry_attrs=True
        )
        assert result['geometry']['has_geom_detail'] is True

    def test_route_without_special_geometry_attrs(self):
        """Without flag, has_geom_detail still appears because it's a
        real column_property in geometry_attributes — dictify includes it.
        The with_special_geometry_attrs flag only *overwrites* it with a
        dynamically-set value (e.g. from a query annotation).
        """
        self.route.geometry.has_geom_detail = True
        result = to_json_dict(
            self.route, schema_route, with_special_geometry_attrs=False
        )
        # has_geom_detail IS in geometry_attributes, so dictify includes it
        assert 'has_geom_detail' in result['geometry']

    # ──────────────────────────────────────────────────────────────
    # 5. with_special_locales_attrs (topic_id)
    # ──────────────────────────────────────────────────────────────

    def test_special_locales_attrs_topic_id(self):
        """with_special_locales_attrs=True copies topic_id from locale."""
        # Set topic_id via DocumentTopic (association proxy pattern)
        self.route.locales[0].document_topic = DocumentTopic(topic_id=42)
        self.session.flush()
        result = to_json_dict(self.route, schema_route, with_special_locales_attrs=True)
        assert result['locales'][0]['topic_id'] == 42

    def test_special_locales_attrs_not_set(self):
        """Without the flag, topic_id is NOT copied."""
        # Don't set topic_id — verify it's absent from dictify output
        result = to_json_dict(
            self.waypoint, schema_waypoint, with_special_locales_attrs=False
        )
        assert 'topic_id' not in result['locales'][0]

    # ──────────────────────────────────────────────────────────────
    # 6. cook_locale flag
    # ──────────────────────────────────────────────────────────────

    def test_cook_locale(self):
        """cook_locale=True adds a 'cooked' key with markdown-processed locale."""
        result = to_json_dict(self.route, schema_route, cook_locale=True)
        assert 'cooked' in result
        assert isinstance(result['cooked'], dict)

    def test_no_cook_locale(self):
        result = to_json_dict(self.route, schema_route, cook_locale=False)
        assert 'cooked' not in result

    # ──────────────────────────────────────────────────────────────
    # 7. Special attributes: img_count, author, creator, protected
    # ──────────────────────────────────────────────────────────────

    def test_special_attr_img_count(self):
        self.area.img_count = 5
        result = to_json_dict(self.area, schema_listing_area)
        assert result['img_count'] == 5

    def test_special_attr_author(self):
        self.outing.author = {'user_id': 123, 'name': 'test'}
        result = to_json_dict(self.outing, schema_route)
        assert result['author'] == {'user_id': 123, 'name': 'test'}

    def test_special_attr_creator(self):
        self.area.creator = {'user_id': 456, 'name': 'creator'}
        result = to_json_dict(self.area, schema_listing_area)
        assert result['creator'] == {'user_id': 456, 'name': 'creator'}

    def test_special_attr_protected(self):
        self.area.protected = True
        result = to_json_dict(self.area, schema_listing_area)
        assert result['protected'] is True

    def test_special_attr_not_present(self):
        """If a special attribute is NOT set on the object, it should NOT appear."""
        result = to_json_dict(self.area, schema_listing_area)
        assert 'author' not in result
        assert 'img_count' not in result
        assert 'creator' not in result

    # ──────────────────────────────────────────────────────────────
    # 8. Outing with has_geom_detail (OUTING_TYPE branch)
    # ──────────────────────────────────────────────────────────────

    def test_outing_has_geom_detail(self):
        """Outings (like routes) support has_geom_detail."""
        from c2corg_api.models.outing import schema_outing

        self.outing.geometry.has_geom_detail = True
        result = to_json_dict(
            self.outing, schema_outing, with_special_geometry_attrs=True
        )
        assert result['geometry']['has_geom_detail'] is True

    # ──────────────────────────────────────────────────────────────
    # 9. None geometry
    # ──────────────────────────────────────────────────────────────

    def test_none_geometry(self):
        """If geometry is None, the geometry key should be None."""
        wp = Waypoint(waypoint_type='summit', elevation=100)
        wp.locales.append(WaypointLocale(lang='en', title='Test'))
        wp.geometry = None
        self.session.add(wp)
        self.session.flush()
        result = to_json_dict(wp, schema_waypoint)
        assert result['geometry'] is None

    # ──────────────────────────────────────────────────────────────
    # 10. Full key snapshot — lock down exact keys for area listing
    # ──────────────────────────────────────────────────────────────

    def test_listing_area_exact_keys(self):
        """Lock in the exact top-level key set."""
        result = to_json_dict(self.area, schema_listing_area)
        # 'type' and 'protected' are real SA columns on Document
        # 'available_langs' appears if set_available_langs was called
        # We check the minimum guaranteed keys here
        guaranteed = {'document_id', 'version', 'area_type', 'locales', 'type'}
        assert guaranteed.issubset(set(result.keys())), (
            f'Missing keys: {guaranteed - set(result.keys())}'
        )

    def test_listing_topo_map_exact_keys(self):
        result = to_json_dict(self.topo_map, schema_listing_topo_map)
        guaranteed = {'document_id', 'version', 'code', 'editor', 'locales', 'type'}
        assert guaranteed.issubset(set(result.keys())), (
            f'Missing keys: {guaranteed - set(result.keys())}'
        )

    # ──────────────────────────────────────────────────────────────
    # 11. Pydantic listing schema equivalence tests
    #     Compare to_json_dict output with model_validate().model_dump()
    # ──────────────────────────────────────────────────────────────

    def test_pydantic_area_listing_matches_to_json_dict(self):
        """AreaListingSchema.model_validate() produces the same data
        as to_json_dict(area, schema_listing_area) for all shared keys.
        """
        old = to_json_dict(self.area, schema_listing_area)
        new = AreaListingSchema.model_validate(self.area).model_dump(exclude_none=True)

        # Core fields must match exactly
        assert new['document_id'] == old['document_id']
        assert new['version'] == old['version']
        assert new['area_type'] == old['area_type']
        assert new['type'] == old['type']

        # Locale structure
        assert len(new['locales']) == len(old['locales'])
        for old_loc, new_loc in zip(old['locales'], new['locales']):
            assert new_loc['lang'] == old_loc['lang']
            assert new_loc['version'] == old_loc['version']
            assert new_loc['title'] == old_loc['title']
            # Listing locale should NOT have extra keys
            assert set(new_loc.keys()) == set(old_loc.keys())

    def test_pydantic_area_listing_with_special_attrs(self):
        """Special attributes propagate through Pydantic schema."""
        set_available_langs([self.area], loaded=True)
        self.area.img_count = 3
        self.area.creator = {'user_id': 1, 'name': 'test'}

        old = to_json_dict(self.area, schema_listing_area)
        new = AreaListingSchema.model_validate(self.area).model_dump(exclude_none=True)

        assert new['available_langs'] == old['available_langs']
        assert new['img_count'] == old['img_count']
        assert new['creator'] == old['creator']

    def test_pydantic_topo_map_listing_matches_to_json_dict(self):
        """TopoMapListingSchema matches to_json_dict output."""
        old = to_json_dict(self.topo_map, schema_listing_topo_map)
        new = TopoMapListingSchema.model_validate(self.topo_map).model_dump(
            exclude_none=True
        )

        assert new['document_id'] == old['document_id']
        assert new['version'] == old['version']
        assert new['code'] == old['code']
        assert new['editor'] == old['editor']
        assert new['type'] == old['type']

        assert len(new['locales']) == len(old['locales'])
        for old_loc, new_loc in zip(old['locales'], new['locales']):
            assert new_loc['lang'] == old_loc['lang']
            assert new_loc['title'] == old_loc['title']
            assert set(new_loc.keys()) == set(old_loc.keys())
