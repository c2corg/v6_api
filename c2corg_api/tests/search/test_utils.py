from c2corg_api.tests import BaseTestCase
from c2corg_api.search.utils import strip_bbcodes


class UtilsTest(BaseTestCase):

    def test_strip_bbcodes(self):
        self.assertEqual(None, strip_bbcodes(None))
        self.assertEqual(
            '  Test   [boom]  <b>',
            strip_bbcodes('[b][i]Test[/i][/b] [boom] [b]<b>')
        )
        self.assertEqual(
            ' mail@to.com ',
            strip_bbcodes('[email]mail@to.com[/email]')
        )
        self.assertEqual(
            ' Link ',
            strip_bbcodes('[url=http://a.bc]Link[/url]')
        )
        self.assertEqual(
            ' Image 1 ',
            strip_bbcodes('[img=123123123_123123123.jpg|inline]Image 1[/img]')
        )
        self.assertEqual(
            ' text with tooltip ',
            strip_bbcodes('[acronym=toootip]text with tooltip[/acronym]')
        )
        self.assertEqual(
            ' ',
            strip_bbcodes('[toc 2 right]')
        )
        self.assertEqual(
            ' colored text ',
            strip_bbcodes('[color=#00AA33]colored text[/color]')
        )
        self.assertEqual(
            ' Text within a quote box ',
            strip_bbcodes('[quote]Text within a quote box[/quote]')
        )
        self.assertEqual(
            '  Image 1  Image 2  Image 3  ',
            strip_bbcodes(
                '[center]'
                '[img=123123123_123123123.jpg|inline]Image 1[/img]'
                '[img=123123123_456123654.jpg|inline]Image 2[/img]'
                '[img=123123123_845135513.jpg|inline]Image 3[/img]'
                '[/center]'
            )
        )
