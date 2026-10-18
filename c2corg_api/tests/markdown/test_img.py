import unittest

from c2corg_api.markdown import parse_code
from c2corg_api.markdown.img import get_image_url, make_image_url_resolver

BASE_URL = 'https://media.example.org/'


class TestImageUrl(unittest.TestCase):

    def test_get_image_url(self):
        self.assertEqual(
            'https://media.example.org/123.jpg',
            get_image_url(BASE_URL, '123.jpg', ''))
        self.assertEqual(
            'https://media.example.org/123MI.jpg',
            get_image_url(BASE_URL, '123.jpg', 'MI'))
        self.assertEqual(
            'https://media.example.org/123BI.png',
            get_image_url(BASE_URL, '123.png', 'BI'))

    def test_get_image_url_svg(self):
        self.assertEqual(
            'https://media.example.org/123.svg',
            get_image_url(BASE_URL, '123.svg', ''))
        self.assertEqual(
            'https://media.example.org/123SI.jpg',
            get_image_url(BASE_URL, '123.svg', 'SI'))


class TestImageTagUrl(unittest.TestCase):

    def setUp(self):  # noqa
        self.resolver = make_image_url_resolver(
            BASE_URL, {1: 'one.jpg', 2: 'two.svg'})

    def test_known_image(self):
        html = parse_code('[img=1/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/oneMI.jpg"', html)
        self.assertIn('c2c:url-proxy="/images/proxy/1?size=MI"', html)

    def test_sizes(self):
        html = parse_code('[img=1 big/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/oneBI.jpg"', html)

        html = parse_code('[img=1 small/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/oneSI.jpg"', html)

        html = parse_code('[img=1 orig/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/one.jpg"', html)
        self.assertIn('c2c:url-proxy="/images/proxy/1"', html)

    def test_svg(self):
        html = parse_code('[img=2/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/twoMI.jpg"', html)

        html = parse_code('[img=2 orig/]', self.resolver)
        self.assertIn('c2c:url="https://media.example.org/two.svg"', html)

    def test_unknown_image(self):
        html = parse_code('[img=3/]', self.resolver)
        self.assertNotIn('c2c:url=', html)
        self.assertIn('c2c:url-proxy="/images/proxy/3?size=MI"', html)

    def test_without_resolver(self):
        html = parse_code('[img=1/]')
        self.assertNotIn('c2c:url=', html)
        self.assertIn('c2c:url-proxy="/images/proxy/1?size=MI"', html)

    def test_resolver_not_kept_between_calls(self):
        parse_code('[img=1/]', self.resolver)
        html = parse_code('[img=1/]')
        self.assertNotIn('c2c:url=', html)

    def test_url_attribute_not_allowed_from_user_html(self):
        # c2c:url is trusted by clients as <img src>, so it must only come
        # from the [img=ID] parser, never from raw HTML
        html = parse_code(
            '<img alt="x" c2c:url="https://evil.example/x.png">',
            self.resolver)
        self.assertNotIn('evil.example', html)
        self.assertNotIn('c2c:url', html)

        html = parse_code(
            '[img=1/]\n\n<img c2c:url="https://evil.example/x.png">',
            self.resolver)
        self.assertEqual(1, html.count('c2c:url='))
        self.assertNotIn('evil.example', html)
