import datetime
import math
from zoneinfo import ZoneInfo

import pytest

from c2corg_api.models.common.attributes import ski_ratings
from c2corg_api.partners import normalise


@pytest.mark.parametrize(
    ('source', 'code', 'expected'),
    [
        ('gulliver', 'skimo', (('skitouring',), False)),
        ('gulliver', 'skisteep', (('skitouring',), True)),
        ('gulliver', 'snowshoe', (('snowshoeing',), False)),
        ('gulliver', 'ciaspole', (('snowshoeing',), False)),
        ('gulliver', 'hike', (('hiking',), False)),
        ('gulliver', 'climb', (('rock_climbing',), False)),
        ('gulliver', 'alpinism', (('mountain_climbing',), False)),
        ('gulliver', 'ice', (('ice_climbing',), False)),
        ('gulliver', 'ferrata', (('via_ferrata',), False)),
        ('gulliver', 'mtb', (('mountain_biking',), False)),
        ('gulliver', ' SkiMo ', (('skitouring',), False)),
        ('gulliver', 'kayak', None),
        ('gulliver', None, None),
        ('gulliver', 12, None),
        ('unknown', 'skimo', None),
        ('skitour', 'anything', None),
    ],
)
def test_map_activity(source, code, expected):
    assert normalise.map_activity(source, code) == expected


def test_activity_map_values_are_c2c_activities():
    from c2corg_api.models.common.attributes import activities

    for table in normalise.ACTIVITY_MAP.values():
        for acts, _steep in table.values():
            assert acts
            assert set(acts) <= set(activities)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('1.1', '1.1'),
        (' 4.3 ', '4.3'),
        (5.6, '5.6'),
        ('5.7', None),
        ('6.1', None),
        ('3', None),
        ('', None),
        ('S3', None),
        (None, None),
        (True, None),
    ],
)
def test_ski_rating(value, expected):
    assert normalise.ski_rating(value) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('MS', ('1.1', '2.3', False)),
        ('BS', ('2.1', '3.3', False)),
        ('OS', ('4.1', '5.6', True)),
        ('BSA', ('2.1', '3.3', False)),
        ('MSA', ('1.1', '2.3', False)),
        ('OSA', ('4.1', '5.6', True)),
        ('os', ('4.1', '5.6', True)),
        (' bsa ', ('2.1', '3.3', False)),
        ('XS', None),
        ('BSAA', None),
        ('', None),
        (None, None),
        (3, None),
    ],
)
def test_blachere(raw, expected):
    assert normalise.blachere(raw) == expected


def test_blachere_table_values_are_c2c_ratings():
    for low, high in normalise.BLACHERE.values():
        assert low in ski_ratings
        assert high in ski_ratings
        assert ski_ratings.index(low) <= ski_ratings.index(high)


@pytest.mark.parametrize(
    ('rating', 'expected'),
    [
        ('1.1', False),
        ('3.3', False),
        ('4.1', True),
        ('5.6', True),
        ('7.1', False),
        (None, False),
    ],
)
def test_is_steep_ski(rating, expected):
    assert normalise.is_steep_ski(rating) is expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('N', ('N',)),
        ('N-NE', ('N', 'NE')),
        ('ne/e', ('NE', 'E')),
        ('S SW, W', ('S', 'SW', 'W')),
        ('N-N', ('N',)),
        ('NNE', ()),
        ('x-y', ()),
        ('N-foo-SE', ('N', 'SE')),
        (['n', 'W', 'zz'], ('N', 'W')),
        ('', ()),
        (None, ()),
        (12, ()),
    ],
)
def test_orientations(raw, expected):
    assert normalise.orientations(raw) == expected


@pytest.mark.parametrize(
    ('html', 'max_len', 'expected'),
    [
        ('plain', 10, 'plain'),
        ('<b>bold</b> text', 50, 'bold text'),
        ('foo<b>bar</b>', 50, 'foobar'),
        ('one<br>two<p>three</p>', 50, 'one two three'),
        ('Tom &amp; Jerry &eacute;t&eacute; &#39;x&#39;', 50, "Tom & Jerry été 'x'"),
        ('&lt;b&gt;kept&lt;/b&gt;', 50, '<b>kept</b>'),
        ('  many \n\t spaces\xa0here ', 50, 'many spaces here'),
        ('abcdefghij', 10, 'abcdefghij'),
        ('abcdefghijk', 10, 'abcdefghi…'),
        ('abcd efgh', 5, 'abcd…'),
        (None, 10, ''),
        ('', 10, ''),
        ('<i></i>', 10, ''),
    ],
)
def test_clean_text(html, max_len, expected):
    result = normalise.clean_text(html, max_len)
    assert result == expected
    assert len(result) <= max_len


@pytest.mark.parametrize(
    ('lon', 'lat', 'expected'),
    [
        (6.86, 45.83, True),
        (-180, -90, True),
        (180, 90, True),
        (0, 0, False),
        (0.0, 0.0, False),
        (0, 45, True),
        (6.8, 0, True),
        (math.nan, 45, False),
        (6, math.nan, False),
        (math.inf, 45, False),
        (181, 45, False),
        (6, 91, False),
        (-181, 0, False),
        (None, 45, False),
        ('6.8', 45, False),
        (True, 45, False),
    ],
)
def test_valid_lonlat(lon, lat, expected):
    assert normalise.valid_lonlat(lon, lat) is expected


def test_local_date_epoch_uses_the_time_zone():
    # 2026-01-10 23:30 UTC is already the 11th in Paris, not in UTC
    epoch = datetime.datetime(2026, 1, 10, 23, 30, tzinfo=datetime.UTC).timestamp()
    assert normalise.local_date(epoch, 'Europe/Paris') == datetime.date(2026, 1, 11)
    assert normalise.local_date(int(epoch), 'UTC') == datetime.date(2026, 1, 10)
    assert normalise.local_date(epoch, ZoneInfo('America/New_York')) == datetime.date(
        2026, 1, 10
    )


def test_local_date_datetime():
    aware = datetime.datetime(2026, 7, 1, 22, 30, tzinfo=datetime.UTC)
    assert normalise.local_date(aware, 'Europe/Paris') == datetime.date(2026, 7, 2)
    naive = datetime.datetime(2026, 7, 1, 22, 30)
    assert normalise.local_date(naive, 'Europe/Paris') == datetime.date(2026, 7, 1)


def test_local_date_date_and_errors():
    assert normalise.local_date(datetime.date(2026, 3, 4), 'UTC') == datetime.date(
        2026, 3, 4
    )
    with pytest.raises(TypeError):
        normalise.local_date(True, 'UTC')
    with pytest.raises(TypeError):
        normalise.local_date(None, 'UTC')
    with pytest.raises(ValueError):
        normalise.local_date('yesterday', 'UTC')
    with pytest.raises(ValueError):
        normalise.local_date('', 'UTC')


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        # gulliver comment_date: local time already
        ('2026-11-23 23:30:00', datetime.date(2026, 11, 23)),
        ('2026-11-23', datetime.date(2026, 11, 23)),
        # an explicit offset is converted
        ('2026-11-23T23:30:00Z', datetime.date(2026, 11, 24)),
        ('2026-11-23T23:30:00+00:00', datetime.date(2026, 11, 24)),
        # an epoch sent as a string (2026-01-10 23:30 UTC)
        (' 1768087800 ', datetime.date(2026, 1, 11)),
    ],
)
def test_local_date_strings(value, expected):
    assert normalise.local_date(value, 'Europe/Paris') == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (5, 5),
        (-3, -3),
        ('42', 42),
        (' 42 ', 42),
        ('42.0', 42),
        ('2345.7', 2346),
        (2345.4, 2345),
        ('abc', None),
        ('', None),
        ('1 200', None),
        (None, None),
        (True, None),
        (math.nan, None),
        (math.inf, None),
        ('nan', None),
        ([1], None),
    ],
)
def test_to_int(value, expected):
    assert normalise.to_int(value) == expected
