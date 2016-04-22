from c2corg_api.search import create_search, get_text_query
from c2corg_api.search.search_filters import create_filter, build_query
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.tests import BaseTestCase
from elasticsearch_dsl.query import Range, Term, Terms, Bool


class AdvancedSearchTest(BaseTestCase):

    def test_build_query(self):
        params = {
            'q': 'search word',
            'we': '1500',
            'a': '1234,4567',
            'l': 'fr'
        }
        meta_params = {
            'limit': 10,
            'offset': 0
        }
        query = build_query(params, meta_params, 'w')
        expected_query = create_search('w'). \
            query(get_text_query('search word')). \
            filter(Term(available_locales='fr')).\
            filter(Terms(areas=[1234, 4567])). \
            filter(Range(elevation={'gte': 1500})). \
            fields([]).\
            extra(from_=0, size=10)
        self.assertQueryEqual(query, expected_query)

    def test_build_query_limit_offset(self):
        params = {
            'q': 'search word'
        }
        meta_params = {
            'limit': 20,
            'offset': 40
        }
        query = build_query(params, meta_params, 'w')
        expected_query = create_search('w'). \
            query(get_text_query('search word')). \
            fields([]).\
            extra(from_=40, size=20)
        self.assertQueryEqual(query, expected_query)

    def test_build_query_sort_outing(self):
        params = {
            'oac': 'skitouring'
        }
        meta_params = {
            'limit': 20,
            'offset': 40
        }
        query = build_query(params, meta_params, 'o')
        expected_query = create_search('o'). \
            filter(Term(activities='skitouring')).\
            fields([]).\
            sort({'date_end': {'order': 'desc'}}).\
            extra(from_=40, size=20)
        self.assertQueryEqual(query, expected_query)

    def assertQueryEqual(self, query1, query2):  # noqa
        q1 = query1.to_dict()
        q2 = query2.to_dict()

        self.assertEqual(q1['fields'], q2['fields'])
        self.assertEqual(q1['from'], q2['from'])
        self.assertEqual(q1['size'], q2['size'])
        self.assertEqual(q1.get('sort'), q2.get('sort'))

        if 'bool' in q1['query'] or 'bool' in q2['query']:
            bool1 = q1['query']['bool']
            bool2 = q2['query']['bool']
            if 'must' in bool1 or 'must' in bool2:
                self.assertEqual(bool1['must'], bool2['must'])
            filters1 = set(str(f) for f in bool1['filter'])
            filters2 = set(str(f) for f in bool2['filter'])
            self.assertEqual(filters1, filters2)
        else:
            self.assertEqual(q1['query'], q2['query'])

    def test_create_filter_range(self):
        self.assertEqual(
            create_filter('not a valid field', '1500,2500', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('we', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('we', 'not a, number', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('we', '1500,2500', SearchWaypoint),
            Range(elevation={'gte': 1500, 'lte': 2500}))
        self.assertEqual(
            create_filter('we', '1500.5,2500.99', SearchWaypoint),
            Range(elevation={'gte': 1500.5, 'lte': 2500.99}))
        self.assertEqual(
            create_filter('we', '1500,', SearchWaypoint),
            Range(elevation={'gte': 1500}))
        self.assertEqual(
            create_filter('we', '1500', SearchWaypoint),
            Range(elevation={'gte': 1500}))
        self.assertEqual(
            create_filter('we', ',2500', SearchWaypoint),
            Range(elevation={'lte': 2500}))
        self.assertEqual(
            create_filter('we', 'NaN,2500', SearchWaypoint),
            Range(elevation={'lte': 2500}))
        self.assertEqual(
            create_filter('we', '1500,NaN', SearchWaypoint),
            Range(elevation={'gte': 1500}))

    def test_create_filter_enum(self):
        self.assertEqual(
            create_filter('wt', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wt', 'invalid type', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wt', 'summit', SearchWaypoint),
            Term(waypoint_type='summit'))
        self.assertEqual(
            create_filter('wt', 'summit,invalid type', SearchWaypoint),
            Term(waypoint_type='summit'))
        self.assertEqual(
            create_filter('wt', 'summit,lake', SearchWaypoint),
            Terms(waypoint_type=['summit', 'lake']))

    def test_create_filter_arrayenum(self):
        self.assertEqual(
            create_filter('wrt', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wrt', 'invalid type', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wrt', 'basalte', SearchWaypoint),
            Term(rock_types='basalte'))
        self.assertEqual(
            create_filter('wrt', 'basalte,invalid type', SearchWaypoint),
            Term(rock_types='basalte'))
        self.assertEqual(
            create_filter('wrt', 'basalte,calcaire', SearchWaypoint),
            Terms(rock_types=['basalte', 'calcaire']))

    def test_create_filter_available_locales(self):
        self.assertEqual(
            create_filter('l', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('l', 'invalid type', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('l', 'en', SearchWaypoint),
            Term(available_locales='en'))
        self.assertEqual(
            create_filter('l', 'en,invalid type', SearchWaypoint),
            Term(available_locales='en'))
        self.assertEqual(
            create_filter('l', 'en,fr', SearchWaypoint),
            Terms(available_locales=['en', 'fr']))

    def test_create_filter_bool(self):
        self.assertEqual(
            create_filter('wp', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wp', 'invalid value', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('wp', 'true', SearchWaypoint),
            Term(has_phone=True))
        self.assertEqual(
            create_filter('wp', 'True', SearchWaypoint),
            Term(has_phone=True))
        self.assertEqual(
            create_filter('wp', '1', SearchWaypoint),
            Term(has_phone=True))
        self.assertEqual(
            create_filter('wp', 'false', SearchWaypoint),
            Term(has_phone=False))
        self.assertEqual(
            create_filter('wp', 'False', SearchWaypoint),
            Term(has_phone=False))
        self.assertEqual(
            create_filter('wp', '0', SearchWaypoint),
            Term(has_phone=False))

    def test_create_filter_area_ids(self):
        self.assertEqual(
            create_filter('a', '', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('a', 'invalid id', SearchWaypoint),
            None)
        self.assertEqual(
            create_filter('a', '123', SearchWaypoint),
            Term(areas=123))
        self.assertEqual(
            create_filter('a', '123,invalid id', SearchWaypoint),
            Term(areas=123))
        self.assertEqual(
            create_filter('a', '123,456', SearchWaypoint),
            Terms(areas=[123, 456]))

    def test_create_filter_date_range(self):
        self.assertEqual(
            create_filter('od', '', SearchOuting),
            None)
        self.assertEqual(
            create_filter('od', 'invalid date', SearchOuting),
            None)
        self.assertEqual(
            create_filter('od', '2016-01-01', SearchOuting),
            Bool(must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'})
            ]))
        self.assertEqual(
            create_filter('od', '2016-01-01,invalid date', SearchOuting),
            Bool(must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'})
            ]))
        self.assertEqual(
            create_filter('od', '2016-01-01,2016-01-01', SearchOuting),
            Bool(must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'})
            ]))
        self.assertEqual(
            create_filter('od', '2016-01-01,2016-01-03', SearchOuting),
            Bool(must_not=Bool(should=[
                Range(date_start={'gt': '2016-01-03'}),
                Range(date_end={'lt': '2016-01-01'})
            ])))
