from c2corg_api.markdown import parse_code
from c2corg_api.markdown.img import get_image_url, make_image_url_resolver

BASE_URL = 'https://media.example.org/'


class TestImageUrl:
    def test_get_image_url(self):
        assert 'https://media.example.org/123.jpg' == get_image_url(
            BASE_URL, '123.jpg', ''
        )
        assert 'https://media.example.org/123MI.jpg' == get_image_url(
            BASE_URL, '123.jpg', 'MI'
        )
        assert 'https://media.example.org/123BI.png' == get_image_url(
            BASE_URL, '123.png', 'BI'
        )

    def test_get_image_url_svg(self):
        assert 'https://media.example.org/123.svg' == get_image_url(
            BASE_URL, '123.svg', ''
        )
        assert 'https://media.example.org/123SI.jpg' == get_image_url(
            BASE_URL, '123.svg', 'SI'
        )


class TestImageTagUrl:
    def setup_method(self):
        self.resolver = make_image_url_resolver(BASE_URL, {1: 'one.jpg', 2: 'two.svg'})

    def test_known_image(self):
        html = parse_code('[img=1/]', self.resolver)
        assert 'c2c:url="https://media.example.org/oneMI.jpg"' in html
        assert 'c2c:url-proxy="/images/proxy/1?size=MI"' in html

    def test_sizes(self):
        html = parse_code('[img=1 big/]', self.resolver)
        assert 'c2c:url="https://media.example.org/oneBI.jpg"' in html

        html = parse_code('[img=1 small/]', self.resolver)
        assert 'c2c:url="https://media.example.org/oneSI.jpg"' in html

        html = parse_code('[img=1 orig/]', self.resolver)
        assert 'c2c:url="https://media.example.org/one.jpg"' in html
        assert 'c2c:url-proxy="/images/proxy/1"' in html

    def test_svg(self):
        html = parse_code('[img=2/]', self.resolver)
        assert 'c2c:url="https://media.example.org/twoMI.jpg"' in html

        html = parse_code('[img=2 orig/]', self.resolver)
        assert 'c2c:url="https://media.example.org/two.svg"' in html

    def test_unknown_image(self):
        html = parse_code('[img=3/]', self.resolver)
        assert 'c2c:url=' not in html
        assert 'c2c:url-proxy="/images/proxy/3?size=MI"' in html

    def test_without_resolver(self):
        html = parse_code('[img=1/]')
        assert 'c2c:url=' not in html
        assert 'c2c:url-proxy="/images/proxy/1?size=MI"' in html

    def test_resolver_not_kept_between_calls(self):
        parse_code('[img=1/]', self.resolver)
        html = parse_code('[img=1/]')
        assert 'c2c:url=' not in html

    def test_url_attribute_not_allowed_from_user_html(self):
        # c2c:url is trusted by clients as <img src>, so it must only come
        # from the [img=ID] parser, never from raw HTML
        html = parse_code(
            '<img alt="x" c2c:url="https://evil.example/x.png">', self.resolver
        )
        assert 'evil.example' not in html
        assert 'c2c:url' not in html

        html = parse_code(
            '[img=1/]\n\n<img c2c:url="https://evil.example/x.png">', self.resolver
        )
        assert 1 == html.count('c2c:url=')
        assert 'evil.example' not in html
