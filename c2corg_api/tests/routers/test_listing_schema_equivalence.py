"""
Equivalence tests — compare old ``to_json_dict`` output with new Pydantic
listing schema output for every document type.

For each type we:
1.  Build a SA model instance with representative data (in-DB for WKB
    round-tripping).
2.  Serialize with ``to_json_dict(obj, schema_listing_<type>)``.
3.  Serialize with ``<Type>ListingSchema.model_validate(obj).model_dump(…)``.
4.  Assert that the key sets and values match.

For route / outing / waypoint the old code uses ``adapt_schema`` to restrict
fields per activity.  The new code uses ``exclude_none=True`` which produces
the same result because unused fields are ``None``.
"""

from datetime import date

from c2corg_api.database import get_db
from c2corg_api.models.area import Area, schema_listing_area
from c2corg_api.models.article import Article, schema_listing_article
from c2corg_api.models.book import Book, schema_listing_book
from c2corg_api.models.coverage import Coverage, schema_listing_coverage
from c2corg_api.models.document import (
    DocumentGeometry,
    DocumentLocale,
    set_available_langs,
)
from c2corg_api.models.image import Image, schema_listing_image
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.topo_map import TopoMap, schema_listing_topo_map
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.xreport import Xreport, XreportLocale, schema_listing_xreport
from c2corg_api.routers.helpers.document_helpers import to_json_dict
from c2corg_api.routers.helpers.document_schemas import (
    adapt_route_schema_for_activities,
    outing_listing_schema_adaptor,
    waypoint_listing_schema_adaptor,
)
from c2corg_api.schemas.listing import (
    AreaListingSchema,
    ArticleListingSchema,
    BookListingSchema,
    CoverageListingSchema,
    ImageListingSchema,
    OutingListingSchema,
    RouteListingSchema,
    TopoMapListingSchema,
    UserProfileListingSchema,  # noqa: F401
    WaypointListingSchema,
    XreportListingSchema,
)
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


def _keys_match(old: dict, new: dict, *, ignore_keys: set | None = None):
    """Assert that ``new`` has at least all keys of ``old``."""
    ignore = ignore_keys or set()
    old_keys = set(old.keys()) - ignore
    new_keys = set(new.keys()) - ignore
    missing = old_keys - new_keys
    assert not missing, f'Keys in old but not new: {missing}'


def _values_match(old: dict, new: dict, keys: list[str]):
    """Assert selected values match between old and new."""
    for k in keys:
        if k in old:
            assert new.get(k) == old[k], (
                f"Mismatch on '{k}': {new.get(k)!r} != {old[k]!r}"
            )


class TestListingSchemaEquivalence(BaseTestCase):
    """Compare old ``to_json_dict`` vs new Pydantic listing schemas."""

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
        # Area
        self.area = Area(area_type='range')
        self.area.locales.append(DocumentLocale(lang='en', title='Chartreuse'))
        self.area.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))'
        )
        self.session.add(self.area)

        # Article
        self.article = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.article.locales.append(
            DocumentLocale(lang='en', title='Trail guide', summary='A great summary')
        )
        self.session.add(self.article)

        # Book
        self.book = Book(activities=['hiking'])
        self.book.locales.append(
            DocumentLocale(lang='en', title='Mountain Book', summary='Book summary')
        )
        self.session.add(self.book)

        # Coverage
        self.coverage = Coverage(coverage_type='fr-idf')
        self.coverage.locales.append(DocumentLocale(lang='en', title='Swiss coverage'))
        self.coverage.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))'
        )
        self.session.add(self.coverage)

        # Image
        self.image = Image(filename='photo.jpg', activities=['hiking'])
        self.image.locales.append(DocumentLocale(lang='en', title='Summit photo'))
        self.image.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.86 45.83)')
        self.session.add(self.image)

        # TopoMap
        self.topo_map = TopoMap(editor='IGN', code='3431OT')
        self.topo_map.locales.append(DocumentLocale(lang='en', title='Grenoble'))
        self.session.add(self.topo_map)

        # UserProfile (special: needs User join — skip for now, tested via integration)

        # Xreport
        self.xreport = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            date=date(2020, 1, 1),
            nb_participants=3,
            elevation=2500,
        )
        self.xreport.locales.append(
            XreportLocale(lang='en', title='Avalanche report', place='Col du Lautaret')
        )
        self.xreport.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.40 45.03)')
        self.session.add(self.xreport)

        # Route
        self.route = Route(
            activities=['skitouring'], elevation_max=4000, elevation_min=1000
        )
        self.route.locales.append(
            RouteLocale(lang='en', title='Voie Normale', title_prefix='Mont Blanc')
        )
        self.route.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.86 45.83)')
        self.session.add(self.route)

        # Outing
        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2024, 1, 15),
            date_end=date(2024, 1, 15),
        )
        self.outing.locales.append(OutingLocale(lang='en', title='Great day out'))
        self.outing.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.86 45.83)')
        self.session.add(self.outing)

        # Waypoint
        self.waypoint = Waypoint(waypoint_type='summit', elevation=4808)
        self.waypoint.locales.append(
            WaypointLocale(lang='en', title='Mont Blanc', access='Chamonix')
        )
        self.waypoint.geometry = DocumentGeometry(geom='SRID=3857;POINT(6.86 45.83)')
        self.session.add(self.waypoint)

        self.session.flush()

        # Set available_langs on all objects
        all_docs = [
            self.area,
            self.article,
            self.book,
            self.coverage,
            self.image,
            self.topo_map,
            self.xreport,
            self.route,
            self.outing,
            self.waypoint,
        ]
        set_available_langs(all_docs, loaded=True)

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _compare(
        self,
        obj,
        old_schema,
        new_schema_cls,
        *,
        exclude_none=False,
        value_keys=None,
        ignore_keys=None,
    ):
        """Core comparison helper."""
        old = to_json_dict(obj, old_schema)
        dump_kw = {'exclude_none': True} if exclude_none else {}
        new = new_schema_cls.model_validate(obj).model_dump(**dump_kw)

        _keys_match(old, new, ignore_keys=ignore_keys)

        if value_keys:
            _values_match(old, new, value_keys)

        # Compare locales structure
        if 'locales' in old and 'locales' in new:
            assert len(new['locales']) == len(old['locales']), (
                f'Locale count mismatch: {len(new["locales"])} != {len(old["locales"])}'
            )
            for old_loc, new_loc in zip(old['locales'], new['locales']):
                _keys_match(old_loc, new_loc)
                _values_match(old_loc, new_loc, ['lang', 'title'])

        # Compare geometry structure
        if 'geometry' in old and old['geometry'] is not None and 'geometry' in new:
            old_geom = old['geometry']
            new_geom = new['geometry']
            assert new_geom is not None, 'New geometry is None but old is not'
            _keys_match(old_geom, new_geom)

        return old, new

    # ──────────────────────────────────────────────────────────────
    # 1. Area
    # ──────────────────────────────────────────────────────────────

    def test_area_equivalence(self):
        old, new = self._compare(
            self.area,
            schema_listing_area,
            AreaListingSchema,
            value_keys=['document_id', 'version', 'area_type', 'available_langs'],
        )

    def test_area_with_special_attrs(self):
        self.area.img_count = 7
        self.area.creator = {'user_id': 1, 'name': 'alice'}
        old, new = self._compare(
            self.area,
            schema_listing_area,
            AreaListingSchema,
            value_keys=['img_count', 'creator'],
        )

    # ──────────────────────────────────────────────────────────────
    # 2. Article
    # ──────────────────────────────────────────────────────────────

    def test_article_equivalence(self):
        old, new = self._compare(
            self.article,
            schema_listing_article,
            ArticleListingSchema,
            value_keys=['document_id', 'categories', 'activities'],
        )

    # ──────────────────────────────────────────────────────────────
    # 3. Book
    # ──────────────────────────────────────────────────────────────

    def test_book_equivalence(self):
        old, new = self._compare(
            self.book,
            schema_listing_book,
            BookListingSchema,
            value_keys=['document_id', 'activities'],
        )

    # ──────────────────────────────────────────────────────────────
    # 4. Coverage
    # ──────────────────────────────────────────────────────────────

    def test_coverage_equivalence(self):
        old, new = self._compare(
            self.coverage,
            schema_listing_coverage,
            CoverageListingSchema,
            value_keys=['document_id', 'coverage_type'],
        )

    # ──────────────────────────────────────────────────────────────
    # 5. Image
    # ──────────────────────────────────────────────────────────────

    def test_image_equivalence(self):
        old, new = self._compare(
            self.image,
            schema_listing_image,
            ImageListingSchema,
            value_keys=['document_id', 'filename'],
        )

    # ──────────────────────────────────────────────────────────────
    # 6. TopoMap
    # ──────────────────────────────────────────────────────────────

    def test_topo_map_equivalence(self):
        old, new = self._compare(
            self.topo_map,
            schema_listing_topo_map,
            TopoMapListingSchema,
            value_keys=['document_id', 'code', 'editor'],
        )

    # ──────────────────────────────────────────────────────────────
    # 7. Xreport
    # ──────────────────────────────────────────────────────────────

    def test_xreport_equivalence(self):
        old, new = self._compare(
            self.xreport,
            schema_listing_xreport,
            XreportListingSchema,
            value_keys=[
                'document_id',
                'elevation',
                'event_type',
                'event_activity',
                'nb_participants',
            ],
        )
        # date needs special handling — old returns date obj, new returns date obj
        assert str(new.get('date')) == str(old.get('date'))

    def test_xreport_geometry(self):
        old = to_json_dict(self.xreport, schema_listing_xreport)
        new = XreportListingSchema.model_validate(self.xreport).model_dump()
        assert old['geometry'] is not None
        assert new['geometry'] is not None
        assert old['geometry']['geom'] is not None
        assert new['geometry']['geom'] is not None

    # ──────────────────────────────────────────────────────────────
    # 8. Route (adapt_schema type — use exclude_none)
    # ──────────────────────────────────────────────────────────────

    def test_route_equivalence(self):
        # Old code uses adapt_schema to get a restricted FieldSpec for skitouring
        old_schema = adapt_route_schema_for_activities(self.route.activities, 'listing')
        old = to_json_dict(self.route, old_schema)
        new = RouteListingSchema.model_validate(self.route).model_dump(
            exclude_none=True
        )

        # new is a subset (exclude_none drops None-valued keys)
        _keys_match(new, old)  # every key in new exists in old
        _values_match(
            old, new, ['document_id', 'activities', 'elevation_max', 'elevation_min']
        )

        # Locales
        assert len(new['locales']) == len(old['locales'])
        for ol, nl in zip(old['locales'], new['locales']):
            _values_match(ol, nl, ['lang', 'title', 'title_prefix'])

    # ──────────────────────────────────────────────────────────────
    # 9. Outing (adapt_schema type — use exclude_none)
    # ──────────────────────────────────────────────────────────────

    def test_outing_equivalence(self):
        from c2corg_api.models.outing import schema_outing

        old_schema = outing_listing_schema_adaptor(schema_outing, self.outing)
        old = to_json_dict(self.outing, old_schema)
        new = OutingListingSchema.model_validate(self.outing).model_dump(
            exclude_none=True
        )

        _keys_match(new, old)  # new is subset of old
        _values_match(old, new, ['document_id', 'activities'])
        assert str(new.get('date_start')) == str(old.get('date_start'))
        assert str(new.get('date_end')) == str(old.get('date_end'))

    # ──────────────────────────────────────────────────────────────
    # 10. Waypoint (adapt_schema type — use exclude_none)
    # ──────────────────────────────────────────────────────────────

    def test_waypoint_equivalence(self):
        from c2corg_api.models.waypoint import schema_waypoint

        old_schema = waypoint_listing_schema_adaptor(schema_waypoint, self.waypoint)
        old = to_json_dict(self.waypoint, old_schema)
        new = WaypointListingSchema.model_validate(self.waypoint).model_dump(
            exclude_none=True
        )

        _keys_match(new, old)  # new is subset of old
        _values_match(old, new, ['document_id', 'waypoint_type', 'elevation'])

    # ──────────────────────────────────────────────────────────────
    # 11. Geometry serialization consistency
    # ──────────────────────────────────────────────────────────────

    def test_point_geometry_geojson_match(self):
        """Point geometry output matches between old and new."""
        old_schema = waypoint_listing_schema_adaptor(None, self.waypoint)
        old = to_json_dict(self.waypoint, old_schema)
        new = WaypointListingSchema.model_validate(self.waypoint).model_dump(
            exclude_none=True
        )

        old_geom = old['geometry']['geom']
        new_geom = new['geometry']['geom']
        assert old_geom is not None
        assert new_geom is not None
        assert old_geom == new_geom

    def test_polygon_geometry_geojson_match(self):
        """Polygon geometry output matches between old and new."""
        old = to_json_dict(self.coverage, schema_listing_coverage)
        new = CoverageListingSchema.model_validate(self.coverage).model_dump()

        old_geom = old['geometry']['geom_detail']
        new_geom = new['geometry']['geom_detail']
        assert old_geom is not None
        assert new_geom is not None
        assert old_geom == new_geom

    # ──────────────────────────────────────────────────────────────
    # 12. available_langs propagation across all types
    # ──────────────────────────────────────────────────────────────

    def test_available_langs_all_types(self):
        """available_langs special attr propagates for every type."""
        cases = [
            (self.area, schema_listing_area, AreaListingSchema),
            (self.article, schema_listing_article, ArticleListingSchema),
            (self.book, schema_listing_book, BookListingSchema),
            (self.coverage, schema_listing_coverage, CoverageListingSchema),
            (self.image, schema_listing_image, ImageListingSchema),
            (self.topo_map, schema_listing_topo_map, TopoMapListingSchema),
            (self.xreport, schema_listing_xreport, XreportListingSchema),
        ]
        for obj, old_schema, new_cls in cases:
            old = to_json_dict(obj, old_schema)
            new = new_cls.model_validate(obj).model_dump()
            assert new.get('available_langs') == old.get('available_langs'), (
                f'available_langs mismatch for {new_cls.__name__}'
            )
