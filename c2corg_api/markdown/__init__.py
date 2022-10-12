import markdown
import bleach
import secrets
import logging
from threading import RLock

from .wikilinks import C2CWikiLinkExtension
from .img import C2CImageExtension
from .video import C2CVideoExtension
from .ltag import C2CLTagExtension
from .header import C2CHeaderExtension
from .ptag import C2CPTagExtension
from .alerts import AlertExtension
from .toc import C2CTocExtension
from .emojis import C2CEmojiExtension
from .nbsp import C2CNbspExtension
from markdown.extensions.nl2br import Nl2BrExtension


logger = logging.getLogger('MARKDOWN')

_PARSER_EXCEPTION_MESSAGE = """
<div c2c:role="danger" style="font-weight:bold">
Parser error, please send a mail to
<a href="mailto:dev@camptocamp.org">dev@camptocamp.org</a>
or post a message on
<a href="https://forum.camptocamp.org/c/site-et-association/v6-suggestions-bugs-et-problemes">
forum</a>.
</div>
"""  # noqa: E501

# RLock because this lock can be released
# only by the thread who acquires it.
_parser_lock = RLock()

_markdown_parser = None
_cleaner = None
_iframe_secret_tag = "iframe_" + secrets.token_hex(32)

"""
_***_secret_tag is used as a private key to replace critical HTML node and
attributes. The key point is this : the parser will use them. bleach will
remove all critical nodes. Then, a very end parser replace secret_tag by good
HTML node/attribute

How to hack C2C ? if you want to inject an iframe, you will need to know the
value of _iframe_secret_tag present into server memory.
"""


def _get_cleaner():
    global _cleaner

    if not _cleaner:
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS + [
            # headers
            "h1", "h2", "h3", "h4", "h5", "h6",

            # blocks
            "div", "p", "pre", "hr", "center",

            # inline nodes
            "span", "br", "sub", "sup", "s", "del", "ins", "small",

            # images
            "figure", "img", "figcaption",

            _iframe_secret_tag,

            # tables
            "table", "tr", "td", "th", "tbody"
        ]

        allowed_attributes = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES)
        allowed_extra_attributes = {
            "a": [
                "c2c:role",
                "c2c:document-type",
                "c2c:document-id",
                "c2c:lang",
                "c2c:slug",
                "c2c:anchor"
            ],
            "h1": ["id", "c2c:role"],
            "h2": ["id", "c2c:role"],
            "h3": ["id", "c2c:role"],
            "h4": ["id", "c2c:role"],
            "h5": ["id", "c2c:role"],
            "h6": ["id", "c2c:role"],
            "table": ["c2c:role"],
            "div": ["class", "style", "c2c:role"],
            "td": ["colspan"],
            "span": ["class", "translate", "id", "c2c:role"],
            _iframe_secret_tag: ["src"],
            "figure": ["c2c:position", "c2c:role", "c2c:size"],
            "img": [
                "alt",
                "c2c:document-id",
                "c2c:role",
                "c2c:size",
                "c2c:url-proxy",
                "c2c:svg-name",
                "c2c:emoji-db"
            ],
        }

        for key in allowed_extra_attributes:
            if key not in allowed_attributes:
                allowed_attributes[key] = []

            allowed_attributes[key] += allowed_extra_attributes[key]

        css_sanitizer = bleach.css_sanitizer.CSSSanitizer(
            allowed_css_properties=bleach.css_sanitizer.ALLOWED_CSS_PROPERTIES + ["clear"])

        _cleaner = bleach.sanitizer.Cleaner(tags=allowed_tags,
                                  attributes=allowed_attributes,
                                  css_sanitizer=css_sanitizer,
                                  protocols=bleach.sanitizer.ALLOWED_PROTOCOLS,
                                  strip=False,
                                  strip_comments=True)

    return _cleaner


def _get_markdown_parser():
    global _markdown_parser
    if not _markdown_parser:
        extensions = [
            C2CWikiLinkExtension(),
            C2CImageExtension(),
            Nl2BrExtension(),
            C2CTocExtension(marker='[toc]', baselevel=2, toc_depth="1-4"),
            C2CVideoExtension(iframe_secret_tag=_iframe_secret_tag),
            C2CLTagExtension(),
            C2CHeaderExtension(),
            C2CPTagExtension(),
            AlertExtension(),
            C2CEmojiExtension(),
            C2CNbspExtension(),
        ]
        _markdown_parser = markdown.Markdown(output_format='xhtml5',
                                             extensions=extensions)

    return _markdown_parser


def parse_code(text):
    """
    Get markdown, and returns HTML.
    This function is thread-safe
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

        try:
            text = parser.convert(text)

            # we keep clean function into thread safe part,
            # because we are not sure of this function
            text = cleaner.clean(text=text)
        except Exception as e:
            logger.exception("While parsing markdown", exc_info=e)
            text = _PARSER_EXCEPTION_MESSAGE

    text = text.replace(_iframe_secret_tag, "iframe")

    return text
