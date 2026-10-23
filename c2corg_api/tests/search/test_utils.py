from c2corg_api.search.utils import strip_bbcodes
from c2corg_api.tests import BaseTestCase


class UtilsTest(BaseTestCase):
    def test_strip_bbcodes(self):
        assert None is strip_bbcodes(None)
        assert '  Test   [boom]  <b>' == strip_bbcodes(
            '[b][i]Test[/i][/b] [boom] [b]<b>'
        )
        assert ' mail@to.com ' == strip_bbcodes('[email]mail@to.com[/email]')
        assert ' Link ' == strip_bbcodes('[url=http://a.bc]Link[/url]')
        assert ' Image 1 ' == strip_bbcodes(
            '[img=123123123_123123123.jpg|inline]Image 1[/img]'
        )
        assert ' text with tooltip ' == strip_bbcodes(
            '[acronym=toootip]text with tooltip[/acronym]'
        )
        assert ' ' == strip_bbcodes('[toc 2 right]')
        assert ' colored text ' == strip_bbcodes('[color=#00AA33]colored text[/color]')
        assert ' Text within a quote box ' == strip_bbcodes(
            '[quote]Text within a quote box[/quote]'
        )
        assert '  Image 1  Image 2  Image 3  ' == strip_bbcodes(
            '[center]'
            '[img=123123123_123123123.jpg|inline]Image 1[/img]'
            '[img=123123123_456123654.jpg|inline]Image 2[/img]'
            '[img=123123123_845135513.jpg|inline]Image 3[/img]'
            '[/center]'
        )
