import pytest

from c2corg_api.markdown import parse_code
from c2corg_api.markdown.img import (
    get_image_url,
    make_image_size_resolver,
    make_image_url_resolver,
)

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


@pytest.fixture
def resolver():
    """Resolve the URLs of the images 1 (JPEG) and 2 (SVG)."""
    return make_image_url_resolver(BASE_URL, {1: 'one.jpg', 2: 'two.svg'})


@pytest.fixture
def url_resolver():
    """Resolve the URL of the image 1."""
    return make_image_url_resolver(BASE_URL, {1: 'one.jpg'})


@pytest.fixture
def size_resolver():
    """Resolve the sizes of the image 1, and the height only of the image 2."""
    return make_image_size_resolver({1: (4000, 3000), 2: (None, 3000)})


class TestImageTagUrl:
    def test_known_image(self, resolver):
        html = parse_code('[img=1/]', resolver)
        assert 'c2c:url="https://media.example.org/oneMI.jpg"' in html
        assert 'c2c:url-proxy="/images/proxy/1?size=MI"' in html

    def test_sizes(self, resolver):
        html = parse_code('[img=1 big/]', resolver)
        assert 'c2c:url="https://media.example.org/oneBI.jpg"' in html

        html = parse_code('[img=1 small/]', resolver)
        assert 'c2c:url="https://media.example.org/oneSI.jpg"' in html

        html = parse_code('[img=1 orig/]', resolver)
        assert 'c2c:url="https://media.example.org/one.jpg"' in html
        assert 'c2c:url-proxy="/images/proxy/1"' in html

    def test_svg(self, resolver):
        html = parse_code('[img=2/]', resolver)
        assert 'c2c:url="https://media.example.org/twoMI.jpg"' in html

        html = parse_code('[img=2 orig/]', resolver)
        assert 'c2c:url="https://media.example.org/two.svg"' in html

    def test_unknown_image(self, resolver):
        html = parse_code('[img=3/]', resolver)
        assert 'c2c:url=' not in html
        assert 'c2c:url-proxy="/images/proxy/3?size=MI"' in html

    def test_without_resolver(self):
        html = parse_code('[img=1/]')
        assert 'c2c:url=' not in html
        assert 'c2c:url-proxy="/images/proxy/1?size=MI"' in html

    def test_resolver_not_kept_between_calls(self, resolver):
        parse_code('[img=1/]', resolver)
        html = parse_code('[img=1/]')
        assert 'c2c:url=' not in html

    def test_url_attribute_not_allowed_from_user_html(self, resolver):
        # c2c:url is trusted by clients as <img src>, so it must only come
        # from the [img=ID] parser, never from raw HTML
        html = parse_code(
            '<img alt="x" c2c:url="https://evil.example/x.png">', resolver
        )
        assert 'evil.example' not in html
        assert 'c2c:url' not in html

        html = parse_code(
            '[img=1/]\n\n<img c2c:url="https://evil.example/x.png">', resolver
        )
        assert 1 == html.count('c2c:url=')
        assert 'evil.example' not in html


class TestImageTagSize:
    def test_known_size(self, url_resolver, size_resolver):
        html = parse_code('[img=1 big/]', url_resolver, size_resolver)
        assert 'c2c:width="4000"' in html
        assert 'c2c:height="3000"' in html
        assert 'c2c:url="https://media.example.org/oneBI.jpg"' in html

    def test_unknown_size(self, url_resolver, size_resolver):
        # an unknown image, or one whose size is not in the database
        for code in ('[img=2/]', '[img=3/]'):
            html = parse_code(code, url_resolver, size_resolver)
            assert 'c2c:width' not in html
            assert 'c2c:height' not in html

    def test_without_size_resolver(self, url_resolver):
        html = parse_code('[img=1/]', url_resolver)
        assert 'c2c:width' not in html

    def test_size_resolver_not_kept_between_calls(self, url_resolver, size_resolver):
        parse_code('[img=1/]', url_resolver, size_resolver)
        html = parse_code('[img=1/]')
        assert 'c2c:width' not in html

    def test_size_attributes_allowed_on_images_only(self, url_resolver):
        html = parse_code('<p c2c:width="5">x</p>', url_resolver)
        assert 'c2c:width' not in html

    def test_size_attributes_not_allowed_from_user_html(
        self, url_resolver, size_resolver
    ):
        # like c2c:url, only the [img=ID] parser gives them
        html = parse_code(
            '<img alt="x" c2c:width="5" c2c:height="9999">',
            url_resolver,
            size_resolver,
        )
        assert 'c2c:width' not in html
        assert 'c2c:height' not in html

        html = parse_code(
            '[img=1/]\n\n<img c2c:width="5">', url_resolver, size_resolver
        )
        assert 1 == html.count('c2c:width=')
        assert 'c2c:width="4000"' in html
