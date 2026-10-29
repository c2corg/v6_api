from c2corg_api.views.validation import parse_int_safe
from c2corg_api.web.compat import parse_if_none_match


class TestIfNoneMatch:
    def test_weak_and_strong_etags(self):
        assert parse_if_none_match('W/"12"') == ('12',)
        assert parse_if_none_match('"a", W/"b"') == ('a', 'b')

    def test_unquoted_value(self):
        assert parse_if_none_match('12') == ('12',)

    def test_none_or_empty(self):
        assert '12' not in parse_if_none_match(None)
        assert '12' not in parse_if_none_match('')

    def test_any(self):
        assert '12' in parse_if_none_match('*')


class TestParseIntSafe:
    def test_values(self):
        assert parse_int_safe('12') == 12
        assert parse_int_safe('abc') is None
        assert parse_int_safe('') is None
        assert parse_int_safe(None) is None
