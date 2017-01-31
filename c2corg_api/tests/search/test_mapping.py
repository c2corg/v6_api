from c2corg_api.models.area import Area
from c2corg_api.models.book import Book
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.article import Article
from c2corg_api.search.mapping_types import QueryableMixin
from c2corg_api.search.mappings.area_mapping import SearchArea
from c2corg_api.search.mappings.book_mapping import SearchBook
from c2corg_api.search.mappings.image_mapping import SearchImage
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.topo_map_mapping import SearchTopoMap
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.mappings.article_mapping import SearchArticle
from c2corg_api.tests import BaseTestCase


class MappingTest(BaseTestCase):

    def test_waypoint_mapping(self):
        self._test_mapping(SearchWaypoint, Waypoint)

        queryable_fields = SearchWaypoint.queryable_fields
        self.assertIn('walt', queryable_fields)
        self.assertTrue(queryable_fields['walt']._range)
        self.assertIn('wtyp', queryable_fields)
        self.assertIsNotNone(queryable_fields['wtyp']._enum)
        self.assertIn('wrock', queryable_fields)
        self.assertIsNotNone(queryable_fields['wrock']._enum)
        self.assertIn('plift', queryable_fields)
        self.assertTrue(queryable_fields['plift']._is_bool)

    def test_route_mapping(self):
        self._test_mapping(SearchRoute, Route)

        queryable_fields = SearchRoute.queryable_fields
        self.assertIn('rmina', queryable_fields)
        self.assertTrue(queryable_fields['rmina']._range)
        self.assertIn('act', queryable_fields)
        self.assertIsNotNone(queryable_fields['act']._enum)
        self.assertIn('dhei', queryable_fields)
        self.assertIn('ralt', queryable_fields)

    def test_outing_mapping(self):
        self._test_mapping(SearchOuting, Outing)

        queryable_fields = SearchOuting.queryable_fields
        self.assertIn('date', queryable_fields)
        self.assertTrue(queryable_fields['date']._date_range)
        self.assertIn('act', queryable_fields)
        self.assertIsNotNone(queryable_fields['act']._enum)

    def test_area_mapping(self):
        self._test_mapping(SearchArea, Area)

        queryable_fields = SearchArea.queryable_fields
        self.assertIn('atyp', queryable_fields)

    def test_image_mapping(self):
        self._test_mapping(SearchImage, Image)

        queryable_fields = SearchImage.queryable_fields
        self.assertIn('idate', queryable_fields)
        self.assertTrue(queryable_fields['idate']._date)
        self.assertIn('act', queryable_fields)
        self.assertIsNotNone(queryable_fields['act']._enum)

    def test_article_mapping(self):
        self._test_mapping(SearchArticle, Article)

        queryable_fields = SearchArticle.queryable_fields
        self.assertIn('act', queryable_fields)
        self.assertIn('acat', queryable_fields)
        self.assertIn('atyp', queryable_fields)

    def test_book_mapping(self):
        self._test_mapping(SearchBook, Book)

        queryable_fields = SearchBook.queryable_fields
        self.assertIn('btyp', queryable_fields)
        self.assertIn('act', queryable_fields)

    def test_map_mapping(self):
        self._test_mapping(SearchTopoMap, TopoMap)

    def test_userprofile_mapping(self):
        self._test_mapping(SearchUser, UserProfile)

    def _test_mapping(self, search_model, model):
        """Test that the fields in a search model (e.g. SearchWaypoint) match
        the fields in the corresponding model (e.g. Waypoint).
        """
        fields = search_model.FIELDS
        mapping_fields = search_model._doc_type.mapping
        for field in fields:
            self.assertTrue(hasattr(model, field))
            self.assertIn(field, mapping_fields)
            mapping_field = mapping_fields[field]

            if isinstance(mapping_field, QueryableMixin):
                if hasattr(mapping_field, '_model_field'):
                    self.assertTrue(
                        mapping_field._model_field is getattr(model, field))
                if hasattr(mapping_field, '_enum_range'):
                    self.assertFalse(
                        mapping_field._enum_range,
                        'Field {0} should be listed as ENUM_RANGE_FIELDS'.
                        format(field)
                    )

        enum_range_fields = search_model.ENUM_RANGE_FIELDS \
            if hasattr(search_model, 'ENUM_RANGE_FIELDS') else []
        for field in enum_range_fields:
            self.assertTrue(hasattr(model, field))
            self.assertIn(field, mapping_fields)
            mapping_field = mapping_fields[field]

            if isinstance(mapping_field, QueryableMixin):
                if hasattr(mapping_field, '_model_field'):
                    self.assertTrue(
                        mapping_field._model_field is getattr(model, field))

        queryable_fields = search_model.queryable_fields
        self.assertIn('qa', queryable_fields)
        self.assertTrue(queryable_fields['qa']._enum)
        self.assertIn('l', queryable_fields)
        self.assertTrue(queryable_fields['l']._enum)
        self.assertIn('a', queryable_fields)
        self.assertTrue(queryable_fields['a']._is_id)
