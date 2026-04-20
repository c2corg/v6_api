import pytest
from elasticsearch_dsl.query import (
    Bool,
    GeoBoundingBox,
    Missing,
    Range,
    Script,
    Term,
    Terms,
)

from c2corg_api.search import create_search, get_text_query_on_title
from c2corg_api.search.mappings.image_mapping import SearchImage
from c2corg_api.search.mappings.outing_mapping import SearchOuting
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.search.mappings.waypoint_mapping import SearchWaypoint
from c2corg_api.search.search_filters import (
    build_query,
    create_bbox_filter,
    create_filter,
)
from c2corg_api.tests import BaseTestCase


def assert_query_equal(query1, query2):
    q1 = query1.to_dict()
    q2 = query2.to_dict()

    assert q1.get('fields') == q2.get('fields')
    assert q1['from'] == q2['from']
    assert q1['size'] == q2['size']
    assert q1.get('sort') == q2.get('sort')

    if 'bool' in q1['query'] or 'bool' in q2['query']:
        bool1 = q1['query']['bool']
        bool2 = q2['query']['bool']

        if 'must' in bool1 or 'must' in bool2:
            assert bool1.get('must') == bool2.get('must')

        if 'should' in bool1 or 'should' in bool2:
            assert bool1.get('should') == bool2.get('should')

        if 'filter' in bool1 or 'filter' in bool2:
            _assert_filters_equal(bool1.get('filter', []), bool2.get('filter', []))
    else:
        assert q1['query'] == q2['query']


def _assert_filters_equal(filters1, filters2):
    assert len(filters1) == len(filters2)

    normal1 = {str(f) for f in filters1 if 'geo_bounding_box' not in f}
    normal2 = {str(f) for f in filters2 if 'geo_bounding_box' not in f}

    assert normal1 == normal2

    bbox1 = [f for f in filters1 if 'geo_bounding_box' in f]
    bbox2 = [f for f in filters2 if 'geo_bounding_box' in f]

    if bbox1 or bbox2:
        assert_bbox_filter_equal(bbox1[0], bbox2[0])


def assert_bbox_filter_equal(f1, f2):
    assert 'geo_bounding_box' in f1
    assert 'geo_bounding_box' in f2

    assert f1['geo_bounding_box'].get('type') == f2['geo_bounding_box'].get('type')

    # assuming the property is named 'geom'
    bbox1 = f1['geo_bounding_box']['geom']
    bbox2 = f2['geo_bounding_box']['geom']
    assert bbox1['left'] == pytest.approx(bbox2['left'])
    assert bbox1['bottom'] == pytest.approx(bbox2['bottom'])
    assert bbox1['right'] == pytest.approx(bbox2['right'])
    assert bbox1['top'] == pytest.approx(bbox2['top'])


class AdvancedSearchTest(BaseTestCase):
    def test_build_query(self):
        params = {'q': 'search word', 'walt': '1500', 'a': '1234,4567', 'l': 'fr'}
        meta_params = {'limit': 10, 'offset': 0}
        query = build_query(params, meta_params, 'w')
        expected_query = (
            create_search('w')
            .query(get_text_query_on_title('search word'))
            .filter(Term(available_locales='fr'))
            .filter(Terms(areas=[1234, 4567]))
            .filter(Range(elevation={'gte': 1500}))
            .fields([])
            .extra(from_=0, size=10)
        )
        assert_query_equal(query, expected_query)

    def test_build_query_bbox(self):
        params = {
            'q': 'search word',
            'walt': '1500',
            'bbox': '699398,5785365,699498,5785465',
        }
        meta_params = {'limit': 10, 'offset': 0}
        query = build_query(params, meta_params, 'w')
        expected_query = (
            create_search('w')
            .query(get_text_query_on_title('search word'))
            .filter(Range(elevation={'gte': 1500}))
            .filter(
                GeoBoundingBox(
                    geom={
                        'left': 6.28279913,
                        'bottom': 46.03129072,
                        'right': 6.28369744,
                        'top': 46.03191439,
                    },
                    type='indexed',
                )
            )
            .fields([])
            .extra(from_=0, size=10)
        )
        assert_query_equal(query, expected_query)

    def test_build_query_limit_offset(self):
        params = {'q': 'search word'}
        meta_params = {'limit': 20, 'offset': 40}
        query = build_query(params, meta_params, 'w')
        expected_query = (
            create_search('w')
            .query(get_text_query_on_title('search word'))
            .fields([])
            .extra(from_=40, size=20)
        )
        assert_query_equal(query, expected_query)

    def test_build_query_sort_outing(self):
        params = {'act': 'skitouring'}
        meta_params = {'limit': 20, 'offset': 40}
        query = build_query(params, meta_params, 'o')
        expected_query = (
            create_search('o')
            .filter(Term(activities='skitouring'))
            .fields([])
            .sort({'date_end': {'order': 'desc'}}, {'id': {'order': 'desc'}})
            .extra(from_=40, size=20)
        )
        assert_query_equal(query, expected_query)

    def test_create_filter_range(self):
        assert create_filter('not a valid field', '1500,2500', SearchWaypoint) is None
        assert create_filter('walt', '', SearchWaypoint) is None
        assert create_filter('walt', 'not a, number', SearchWaypoint) is None
        assert create_filter('walt', '1500,2500', SearchWaypoint) == Range(
            elevation={'gte': 1500, 'lte': 2500}
        )
        assert create_filter('walt', '1500.5,2500.99', SearchWaypoint) == Range(
            elevation={'gte': 1500.5, 'lte': 2500.99}
        )
        assert create_filter('walt', '1500,', SearchWaypoint) == Range(
            elevation={'gte': 1500}
        )
        assert create_filter('walt', '1500', SearchWaypoint) == Range(
            elevation={'gte': 1500}
        )
        assert create_filter('walt', ',2500', SearchWaypoint) == Range(
            elevation={'lte': 2500}
        )
        assert create_filter('walt', 'NaN,2500', SearchWaypoint) == Range(
            elevation={'lte': 2500}
        )
        assert create_filter('walt', '1500,NaN', SearchWaypoint) == Range(
            elevation={'gte': 1500}
        )

    def test_create_filter_enum_range(self):
        assert (
            create_filter('not a valid field', 'medium,great', SearchWaypoint) is None
        )
        assert create_filter('qa', '', SearchWaypoint) is None
        assert create_filter('qa', 'not a, valid enum', SearchWaypoint) is None
        assert create_filter('qa', 'medium,great', SearchWaypoint) == Range(
            quality={'gte': 2, 'lte': 4}
        )
        assert create_filter('qa', 'medium,', SearchWaypoint) == Range(
            quality={'gte': 2}
        )
        assert create_filter('qa', 'medium', SearchWaypoint) == Range(
            quality={'gte': 2}
        )
        assert create_filter('qa', ',great', SearchWaypoint) == Range(
            quality={'lte': 4}
        )
        assert create_filter('qa', 'invalid enum,great', SearchWaypoint) == Range(
            quality={'lte': 4}
        )
        assert create_filter('qa', 'medium,invalid enum', SearchWaypoint) == Range(
            quality={'gte': 2}
        )

    def test_create_filter_enum_range_min_max(self):
        assert create_filter('not a valid field', '4b,6c', SearchWaypoint) is None
        assert create_filter('crat', '', SearchWaypoint) is None
        assert create_filter('crat', 'invalid term', SearchWaypoint) is None
        assert create_filter('crat', '4b', SearchWaypoint) is None
        assert create_filter('crat', '4b,invalid term', SearchWaypoint) is None
        assert create_filter('crat', 'invalid term,6c', SearchWaypoint) is None
        assert create_filter('crat', '4b,6c', SearchWaypoint) == Bool(
            must_not=Bool(
                should=[
                    Range(climbing_rating_min={'gt': 17}),
                    Range(climbing_rating_max={'lt': 5}),
                    Bool(
                        must=[
                            Missing(field='climbing_rating_min'),
                            Missing(field='climbing_rating_max'),
                        ]
                    ),
                ]
            )
        )

    def test_create_filter_integer_range(self):
        assert create_filter('not a valid field', '1200,2400', SearchRoute) is None
        assert create_filter('ele', '', SearchRoute) is None
        assert create_filter('ele', 'invalid term', SearchRoute) is None
        assert create_filter('ele', '1200', SearchRoute) is None
        assert create_filter('ele', '1200,invalid term', SearchRoute) is None
        assert create_filter('ele', 'invalid term,2400', SearchRoute) is None
        assert create_filter('ele', '1200,2400', SearchRoute) == Bool(
            must_not=Bool(
                should=[
                    Range(elevation_min={'gt': 2400}),
                    Range(elevation_max={'lt': 1200}),
                    Bool(
                        must=[
                            Missing(field='elevation_min'),
                            Missing(field='elevation_max'),
                        ]
                    ),
                ]
            )
        )
        assert create_filter('height', '1200,2400', SearchWaypoint) == Bool(
            must_not=Bool(
                should=[
                    Range(height_min={'gt': 2400}),
                    Range(height_max={'lt': 1200}),
                    Bool(
                        must=[Missing(field='height_min'), Missing(field='height_max')]
                    ),
                ]
            )
        )

    def test_create_filter_enum(self):
        assert create_filter('wtyp', '', SearchWaypoint) is None
        assert create_filter('wtyp', 'invalid type', SearchWaypoint) is None
        assert create_filter('wtyp', 'summit', SearchWaypoint) == Term(
            waypoint_type='summit'
        )
        assert create_filter('wtyp', 'summit,invalid type', SearchWaypoint) == Term(
            waypoint_type='summit'
        )
        assert create_filter('wtyp', 'summit,lake', SearchWaypoint) == Terms(
            waypoint_type=['summit', 'lake']
        )

    def test_create_filter_arrayenum(self):
        assert create_filter('wrock', '', SearchWaypoint) is None
        assert create_filter('wrock', 'invalid type', SearchWaypoint) is None
        assert create_filter('wrock', 'basalte', SearchWaypoint) == Term(
            rock_types='basalte'
        )
        assert create_filter('wrock', 'basalte,invalid type', SearchWaypoint) == Term(
            rock_types='basalte'
        )
        assert create_filter('wrock', 'basalte,calcaire', SearchWaypoint) == Terms(
            rock_types=['basalte', 'calcaire']
        )

    def test_create_filter_available_locales(self):
        assert create_filter('l', '', SearchWaypoint) is None
        assert create_filter('l', 'invalid type', SearchWaypoint) is None
        assert create_filter('l', 'en', SearchWaypoint) == Term(available_locales='en')
        assert create_filter('l', 'en,invalid type', SearchWaypoint) == Term(
            available_locales='en'
        )
        assert create_filter('l', 'en,fr', SearchWaypoint) == Terms(
            available_locales=['en', 'fr']
        )

    def test_create_filter_bool(self):
        assert create_filter('plift', '', SearchWaypoint) is None
        assert create_filter('plift', 'invalid value', SearchWaypoint) is None
        assert create_filter('plift', 'true', SearchWaypoint) == Term(lift_access=True)
        assert create_filter('plift', 'True', SearchWaypoint) == Term(lift_access=True)
        assert create_filter('plift', '1', SearchWaypoint) == Term(lift_access=True)
        assert create_filter('plift', 'false', SearchWaypoint) == Term(
            lift_access=False
        )
        assert create_filter('plift', 'False', SearchWaypoint) == Term(
            lift_access=False
        )
        assert create_filter('plift', '0', SearchWaypoint) == Term(lift_access=False)

    def test_create_filter_area_ids(self):
        assert create_filter('a', '', SearchWaypoint) is None
        assert create_filter('a', 'invalid id', SearchWaypoint) is None
        assert create_filter('a', '123', SearchWaypoint) == Term(areas=123)
        assert create_filter('a', '123,invalid id', SearchWaypoint) == Term(areas=123)
        assert create_filter('a', '123,456', SearchWaypoint) == Terms(areas=[123, 456])

    def test_create_filter_date_range(self):
        assert create_filter('date', '', SearchOuting) is None
        assert create_filter('date', 'invalid date', SearchOuting) is None
        assert create_filter('date', '2016-01-01', SearchOuting) == Bool(
            must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'}),
            ]
        )
        assert create_filter('date', '2016-01-01,invalid date', SearchOuting) == Bool(
            must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'}),
            ]
        )
        assert create_filter('date', '2016-01-01,2016-01-01', SearchOuting) == Bool(
            must=[
                Range(date_start={'lte': '2016-01-01'}),
                Range(date_end={'gte': '2016-01-01'}),
            ]
        )
        assert create_filter('date', '2016-01-01,2016-01-03', SearchOuting) == Bool(
            must_not=Bool(
                should=[
                    Range(date_start={'gt': '2016-01-03'}),
                    Range(date_end={'lt': '2016-01-01'}),
                ]
            )
        )

    def test_create_filter_period(self):
        assert create_filter('period', '', SearchOuting) is None
        assert create_filter('period', 'invalid date', SearchOuting) is None
        assert create_filter('period', '10-01', SearchOuting) is None
        assert create_filter('period', '10-01,09-02', SearchOuting) is None
        assert create_filter('period', '2016-10-01', SearchOuting) is None
        assert create_filter('period', '2016-10-01, 12-31', SearchOuting) is None
        assert create_filter('period', '12-31, 2016-10-01', SearchOuting) is None

        script_expected_string = "doc['date_end'].value%31556952000 >= min && doc['date_start'].value%31556952000 <= max"  # noqa: E501

        assert create_filter('period', '2016-01-02,2019-01-02', SearchOuting) == Script(
            script=script_expected_string, params={'min': 73008000, 'max': 96552000}
        )
        assert create_filter('period', '2017-10-04,2016-10-10', SearchOuting) == Script(
            script=script_expected_string,
            params={'min': 23898456000, 'max': 24437808000},
        )

    def test_create_filter_date(self):
        assert create_filter('idate', '', SearchImage) is None
        assert create_filter('idate', 'invalid date', SearchImage) is None
        assert create_filter('idate', '2016-01-01', SearchImage) == Range(
            date_time={'gte': '2016-01-01', 'lte': '2016-01-01'}
        )
        assert create_filter('idate', '2016-01-01,invalid date', SearchImage) == Range(
            date_time={'gte': '2016-01-01', 'lte': '2016-01-01'}
        )
        assert create_filter('idate', '2016-01-01,2016-01-01', SearchImage) == Range(
            date_time={'gte': '2016-01-01', 'lte': '2016-01-01'}
        )
        assert create_filter('idate', '2016-01-01,2016-01-03', SearchImage) == Range(
            date_time={'gte': '2016-01-01', 'lte': '2016-01-03'}
        )

    def test_create_bbox_filter(self):
        assert create_bbox_filter('') is None
        assert create_bbox_filter('a,b,c,d') is None
        assert create_bbox_filter('1,2,3') is None
        assert create_bbox_filter('1,2,3,d') is None
        assert create_bbox_filter('NaN,NaN,NaN,NaN') is None
        assert create_bbox_filter('650000,4500000,650000,5700000') is None
        assert create_bbox_filter('500000,5700000,650000,5700000') is None
        assert create_bbox_filter('650000,5700000,650000,5700000') is None
        assert_bbox_filter_equal(
            create_bbox_filter('699398,5785365,699498,5785465').to_dict(),
            GeoBoundingBox(
                geom={
                    'left': 6.28279913,
                    'bottom': 46.03129072,
                    'right': 6.28369744,
                    'top': 46.03191439,
                },
                type='indexed',
            ).to_dict(),
        )
