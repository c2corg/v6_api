import logging
import re
import secrets
from threading import RLock

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
from .wikilinks import C2CWikiLinkExtension

logger = logging.getLogger('MARKDOWN')

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

"""
_***_secret_tag is used as a private key to replace critical HTML node and
attributes. The key point is this : the parser will use them. nh3 will
remove all critical nodes. Then, a very end parser replace secret_tag by good
HTML node/attribute

How to hack C2C ? if you want to inject an iframe, you will need to know the
value of _iframe_secret_tag present into server memory.

Same for the c2c:url attribute of embedded images, which clients may use as
<img src>: only the [img=ID] parser can produce it, a c2c:url attribute written
in raw HTML is removed by nh3.
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
            # keep links as written (nh3 adds rel="noopener noreferrer")
            link_rel=None,
        )

    return _cleaner


def _get_markdown_parser():
    global _markdown_parser
    if not _markdown_parser:
        extensions = [
            C2CWikiLinkExtension(),
            C2CImageExtension(url_secret_attribute=_img_url_secret_attribute),
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


def parse_code(text, image_url_resolver=None):
    """Get markdown, and returns HTML.

    This function is thread-safe.

    `image_url_resolver` is an optional function
    `(document_id, size) -> url or None` giving the direct media URL of
    embedded images (see `img.make_image_url_resolver`).
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

    text = text.replace(_iframe_secret_tag, 'iframe')
    text = text.replace(_img_url_secret_attribute, 'c2c:url')

    return text
