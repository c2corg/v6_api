import html
import logging
import re
import secrets
from threading import RLock
from urllib.parse import urlsplit

import markdown
import nh3
from markdown.extensions.nl2br import Nl2BrExtension

from .alerts import AlertExtension
from .emojis import C2CEmojiExtension
from .header import C2CHeaderExtension
from .img import C2CImageExtension
from .ltag import C2CLTagExtension
from .nbsp import C2CNbspExtension
from .ptag import C2CPTagExtension
from .toc import C2CTocExtension
from .video import C2CVideoExtension
from .wikilinks import SITE_URL_RE, C2CWikiLinkExtension

logger = logging.getLogger('MARKDOWN')

# (the parameter `html` of some functions hides the module)
_unescape = html.unescape

# an opening <a> tag of the cleaned HTML (attribute values are quoted)
_LINK_TAG_PATTERN = re.compile(r'<a\s((?:[^>"]|"[^"]*")*)>')
_HREF_PATTERN = re.compile(r'\bhref="(https?://[^"/?#]*)[^"]*"', re.IGNORECASE)
# the user part and the port of a link host
_HOST_PATTERN = re.compile(r'^https?://(?:[^@]*@)?([^:]*)', re.IGNORECASE)
_EXTERNAL_LINK_REL = 'nofollow ugc'
# the whole URL of a link of the cleaned HTML
_URL_HREF_PATTERN = re.compile(r'\bhref="(https?://[^"]*)"', re.IGNORECASE)
# longer URLs (in bytes) are not tracked: an index entry has a size limit
MAX_TRACKED_URL_LENGTH = 2000

_PARSER_EXCEPTION_MESSAGE = """
<div c2c:role="danger" style="font-weight:bold">
Parser error, please send a mail to
<a href="mailto:dev@camptocamp.org">dev@camptocamp.org</a>
or post a message on
<a href="https://forum.camptocamp.org/c/site-et-association/v6-suggestions-bugs-et-problemes">
forum</a>.
</div>
"""

# RLock because this lock can be released
# only by the thread who acquires it.
_parser_lock = RLock()

_markdown_parser = None
_cleaner = None
_iframe_secret_tag = 'iframe_' + secrets.token_hex(32)
_img_url_secret_attribute = 'c2c:url-' + secrets.token_hex(32)
_img_width_secret_attribute = 'c2c:width-' + secrets.token_hex(32)
_img_height_secret_attribute = 'c2c:height-' + secrets.token_hex(32)

"""
_***_secret_tag is used as a private key to replace critical HTML node and
attributes. The key point is this : the parser will use them. nh3 will
remove all critical nodes. Then, a very end parser replace secret_tag by good
HTML node/attribute

How to hack C2C ? if you want to inject an iframe, you will need to know the
value of _iframe_secret_tag present into server memory.

Same for the c2c:url attribute of embedded images, which clients may use as
<img src>: only the [img=ID] parser can produce it, a c2c:url attribute written
in raw HTML is removed by nh3. The same for c2c:width and c2c:height, the size
of the original image, which clients use to keep the space of the image.
"""


# bleach's default allow-lists, which this sanitizer extends (kept as they
# were with bleach 6.4 so that the output does not change)
_DEFAULT_TAGS = frozenset(
    {
        'a',
        'abbr',
        'acronym',
        'b',
        'blockquote',
        'code',
        'em',
        'i',
        'li',
        'ol',
        'strong',
        'ul',
    }
)
_DEFAULT_ATTRIBUTES = {'a': ['href', 'title'], 'abbr': ['title'], 'acronym': ['title']}
_URL_SCHEMES = frozenset({'http', 'https', 'mailto'})
_CSS_PROPERTIES = frozenset(
    {
        'azimuth',
        'background-color',
        'border-bottom-color',
        'border-collapse',
        'border-color',
        'border-left-color',
        'border-right-color',
        'border-top-color',
        'clear',
        'color',
        'cursor',
        'direction',
        'display',
        'elevation',
        'float',
        'font',
        'font-family',
        'font-size',
        'font-style',
        'font-variant',
        'font-weight',
        'height',
        'letter-spacing',
        'line-height',
        'overflow',
        'pause',
        'pause-after',
        'pause-before',
        'pitch',
        'pitch-range',
        'richness',
        'speak',
        'speak-header',
        'speak-numeral',
        'speak-punctuation',
        'speech-rate',
        'stress',
        'text-align',
        'text-decoration',
        'text-indent',
        'unicode-bidi',
        'vertical-align',
        'voice-family',
        'volume',
        'white-space',
        'width',
    }
)

_allowed_tags = None

# start of an HTML tag (`<name` or `</name`) and its name
_TAG_START_RE = re.compile(r'<(/?)([A-Za-z][^\s/>]*)')


def _escape_disallowed_tags(html):
    """Escape the tags that the sanitizer would remove, so they show as text."""

    # nh3 removes disallowed tags (bleach could escape them). Escaping their
    # `<` first keeps what users typed visible, e.g. `<www.example.com>` or
    # `<script>`. This only affects presentation: nh3 still sanitizes the
    # result.
    def escape(match):
        if match.group(2).lower() in _allowed_tags:
            return match.group(0)
        return '&lt;' + match.group(1) + match.group(2)

    return _TAG_START_RE.sub(escape, html)


def _get_cleaner():
    global _cleaner, _allowed_tags

    if not _cleaner:
        allowed_tags = _DEFAULT_TAGS.union(
            {
                # headers
                'h1',
                'h2',
                'h3',
                'h4',
                'h5',
                'h6',
                # blocks
                'div',
                'p',
                'pre',
                'hr',
                'center',
                # inline nodes
                'span',
                'br',
                'sub',
                'sup',
                's',
                'del',
                'ins',
                'small',
                # images
                'figure',
                'img',
                'figcaption',
                _iframe_secret_tag,
                # tables
                'table',
                'tr',
                'td',
                'th',
                'tbody',
            }
        )

        allowed_attributes = {
            tag: list(attributes) for tag, attributes in _DEFAULT_ATTRIBUTES.items()
        }
        allowed_extra_attributes = {
            'a': [
                'c2c:role',
                'c2c:document-type',
                'c2c:document-id',
                'c2c:lang',
                'c2c:slug',
                'c2c:anchor',
            ],
            'h1': ['id', 'c2c:role'],
            'h2': ['id', 'c2c:role'],
            'h3': ['id', 'c2c:role'],
            'h4': ['id', 'c2c:role'],
            'h5': ['id', 'c2c:role'],
            'h6': ['id', 'c2c:role'],
            'table': ['c2c:role'],
            'div': ['class', 'style', 'c2c:role'],
            'td': ['colspan'],
            'span': ['class', 'translate', 'id', 'c2c:role'],
            _iframe_secret_tag: ['src'],
            'figure': ['c2c:position', 'c2c:role', 'c2c:size'],
            'img': [
                'alt',
                'c2c:document-id',
                'c2c:role',
                'c2c:size',
                'c2c:url-proxy',
                _img_url_secret_attribute,
                _img_width_secret_attribute,
                _img_height_secret_attribute,
                'c2c:svg-name',
                'c2c:emoji-db',
            ],
        }

        for key in allowed_extra_attributes:
            if key not in allowed_attributes:
                allowed_attributes[key] = []

            allowed_attributes[key] += allowed_extra_attributes[key]

        _allowed_tags = allowed_tags
        _cleaner = nh3.Cleaner(
            tags=set(allowed_tags),
            # no attribute is allowed on every tag (nh3 allows `lang` and
            # `title` by default)
            attributes={
                '*': set(),
                **{tag: set(attrs) for tag, attrs in allowed_attributes.items()},
            },
            filter_style_properties=set(_CSS_PROPERTIES),
            url_schemes=set(_URL_SCHEMES),
            strip_comments=True,
            # no rel from nh3 ("noopener noreferrer" on every link):
            # _mark_external_links adds one to the links to other sites
            link_rel=None,
        )

    return _cleaner


def _get_markdown_parser():
    global _markdown_parser
    if not _markdown_parser:
        extensions = [
            C2CWikiLinkExtension(),
            C2CImageExtension(
                url_secret_attribute=_img_url_secret_attribute,
                width_secret_attribute=_img_width_secret_attribute,
                height_secret_attribute=_img_height_secret_attribute,
            ),
            Nl2BrExtension(),
            C2CTocExtension(marker='[toc]', baselevel=2, toc_depth='1-4'),
            C2CVideoExtension(iframe_secret_tag=_iframe_secret_tag),
            C2CLTagExtension(),
            C2CHeaderExtension(),
            C2CPTagExtension(),
            AlertExtension(),
            C2CEmojiExtension(),
            C2CNbspExtension(),
        ]
        _markdown_parser = markdown.Markdown(
            output_format='xhtml5', extensions=extensions
        )

    return _markdown_parser


def parse_code(
    text,
    image_url_resolver=None,
    image_size_resolver=None,
    link_type_resolver=None,
    credited_urls=None,
):
    """Get markdown, and returns HTML.

    This function is thread-safe.

    `image_url_resolver` is an optional function
    `(document_id, size) -> url or None` giving the direct media URL of
    embedded images (see `img.make_image_url_resolver`), and
    `image_size_resolver` an optional `document_id -> (width, height) or None`
    giving the size of their original (see `img.make_image_size_resolver`).
    `link_type_resolver` is an optional `document_id -> type or None` giving
    the type of the documents of the [[type/id|label]] links ("routes"...):
    a link with another type is built with it.
    `credited_urls` is an optional set of the URLs of other sites that the
    search engines may credit: their links get no rel="nofollow ugc" (see
    linkcheck.rel).
    """
    # we need parsing to be thread safe because
    # L numbering, and Markdown() has internal global variables

    # for explanation about Lock context manager usage
    # see https://docs.python.org/3/library/threading.html
    # on paragraph 17.1.10 (with statement)
    with _parser_lock:
        parser = _get_markdown_parser()
        cleaner = _get_cleaner()

        # reset parser state. Otherwise, internals parser cache grows
        # indefinitely, and performance decreases over time
        parser.reset()
        parser.c2c_image_url_resolver = image_url_resolver
        parser.c2c_image_size_resolver = image_size_resolver
        parser.c2c_link_type_resolver = link_type_resolver

        try:
            text = parser.convert(text)

            # we keep clean function into thread safe part,
            # because we are not sure of this function
            text = cleaner.clean(_escape_disallowed_tags(text))
        except Exception as e:
            logger.exception('While parsing markdown', exc_info=e)
            text = _PARSER_EXCEPTION_MESSAGE
        finally:
            parser.c2c_image_url_resolver = None
            parser.c2c_image_size_resolver = None
            parser.c2c_link_type_resolver = None

    text = _mark_external_links(text, credited_urls or ())
    text = text.replace(_iframe_secret_tag, 'iframe')
    text = text.replace(_img_url_secret_attribute, 'c2c:url')
    text = text.replace(_img_width_secret_attribute, 'c2c:width')
    text = text.replace(_img_height_secret_attribute, 'c2c:height')

    return text


def _is_external_host(host):
    host = host.lower().rstrip('.')
    return host != 'camptocamp.org' and not host.endswith('.camptocamp.org')


def _mark_external_links(html, credited_urls=()):
    """Add rel="nofollow ugc" to the links of the cleaned HTML to other sites."""
    # Links written by users: search engines must not credit the sites they
    # lead to (an expired domain bought by a spammer, for instance). Links to
    # camptocamp.org and its subdomains, and wikilinks, are left as they are.
    # The cleaner drops any rel attribute written in the text.

    def mark(match):
        href = _HREF_PATTERN.search(match.group(1))
        if not href:
            return match.group(0)
        host = _HOST_PATTERN.match(href.group(1)).group(1)
        if not _is_external_host(host):
            return match.group(0)
        # a link known to be genuine (see linkcheck.rel)
        url = _URL_HREF_PATTERN.search(match.group(1))
        if url and _unescape(url.group(1)) in credited_urls:
            return match.group(0)
        return f'<a {match.group(1)} rel="{_EXTERNAL_LINK_REL}">'

    return _LINK_TAG_PATTERN.sub(mark, html)


def get_embedded_image_ids(text):
    """Return the ids of the images that `parse_code` shows in a text, in order."""
    return get_text_references(text)[0]


def get_text_references(text):
    """Return the images shown and the links of a text: (ids, links, urls)."""
    # The same parser as parse_code(), whose [img=ID] processor collects the
    # ids of the images it builds (see img.C2CImageBlock): a tag it does not
    # turn into an image (inside raw HTML, in the middle of a line, with
    # uppercase letters...) is not shown, so it is not counted either. The
    # links are the [[type/id|label]] and the full URLs of the site that it
    # turns into links (see wikilinks.C2CLinkCollector): (type as written,
    # id, written as a URL), in order. The urls are the other http(s) links
    # of the cooked text (see _get_external_urls).
    with _parser_lock:
        parser = _get_markdown_parser()
        parser.reset()
        ids = []
        links = []
        parser.c2c_embedded_image_ids = ids
        parser.c2c_linked_documents = links
        try:
            converted = parser.convert(text)
            cleaned = _get_cleaner().clean(_escape_disallowed_tags(converted))
        except Exception as e:
            # parse_code() shows an error message instead of the text
            logger.exception('While parsing markdown', exc_info=e)
            return [], [], []
        finally:
            parser.c2c_embedded_image_ids = None
            parser.c2c_linked_documents = None

    return ids, links, _get_external_urls(cleaned)


def get_url_host(url):
    """Return the host of an http(s) URL, lowercase, or None."""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    host = (host or '').rstrip('.')
    return host or None


def _get_external_urls(cleaned_html):
    """Return the URLs of the links of the cooked HTML, but the documents."""
    # As the reader gets them: markdown and raw HTML links, after the cleaner
    # (no javascript: link...). The full URLs of the documents of the site
    # are document links (see wikilinks.C2CLinkCollector); the other URLs of
    # the site (forum, media...) are kept. Each URL once, in order.
    urls = []
    for tag in _LINK_TAG_PATTERN.finditer(cleaned_html):
        href = _URL_HREF_PATTERN.search(tag.group(1))
        if not href:
            continue
        url = html.unescape(href.group(1))
        if (
            len(url.encode()) > MAX_TRACKED_URL_LENGTH
            or SITE_URL_RE.match(url)
            or not get_url_host(url)
            or url in urls
        ):
            continue
        urls.append(url)
    return urls
