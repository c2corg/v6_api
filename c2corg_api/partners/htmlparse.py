"""HTML helpers for the adapters of the sites that publish no JSON.

A sturdy, selector-based parse (BeautifulSoup on the stdlib `html.parser`, CSS
selectors by soupsieve): an adapter reads its fields through selectors, never by
position, so a reordered page or a new column does not shift the values.

The selectors an adapter reads (`REQUIRED_SELECTORS`, see `contract.py`) are also
the allow-list of what a recording keeps (`trim`): the elements they match with
their content, and only the tags of their ancestors. Any other text of the page
(narratives, comments, titles of photos...) never reaches a fixture.
"""

import re
from collections.abc import Collection

from bs4 import BeautifulSoup, Comment
from bs4.element import Tag

PARSER = 'html.parser'
_SPACES = re.compile(r'\s+')
# never kept in a recording: media, scripts, frames
_DROP_TAGS = frozenset(
    {'img', 'picture', 'source', 'video', 'audio', 'script', 'style', 'iframe'}
    | {'svg', 'noscript', 'link', 'meta', 'canvas', 'object', 'embed'}
)
_VOID_TAGS = frozenset({'link', 'meta', 'br', 'hr', 'img', 'input', 'source', 'wbr'})
# attributes dropped from the matched elements (inline styles, media urls and
# big JSON blobs of the page widgets)
_DROP_ATTRS = frozenset({'style', 'src', 'srcset', 'onerror', 'data-calques'})
# the only attributes kept on the ancestors of the matched elements
_ANCESTOR_ATTRS = ('id', 'class', 'data-sport')


def parse(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, PARSER)


def text_of(node: Tag | None) -> str:
    """Return the text of an element, spaces collapsed ('' for None)."""
    if node is None:
        return ''
    return _SPACES.sub(' ', node.get_text(' ').replace('\xa0', ' ')).strip()


def matches(text: str, selectors: Collection[str]) -> dict[str, str]:
    """Return `{selector: 'str'}` for each selector matching the page.

    The shape of an HTML page, in the format of `shapes.shape` (a key that is
    there means the selector matched something).
    """
    soup = parse(text)
    return {s: 'str' for s in sorted(selectors) if soup.select_one(s) is not None}


def trim(text: str, selectors: Collection[str]) -> str:
    """Keep only what `selectors` match, and their ancestors' bare tags.

    The result is a page with the same structure around the matched elements
    (so the same selectors still match) and nothing else: no text outside the
    matched elements, no media, no scripts, no comments. Idempotent.
    """
    soup = parse(text)
    # an unclosed void element (`<link>`) swallows what follows it: the markup
    # is repaired, so that the same structure comes back from a recording
    for tag in soup.find_all(_VOID_TAGS):
        if tag.contents:
            tag.unwrap()
    matched: list[Tag] = []
    for selector in selectors:
        matched.extend(soup.select(selector))
    matched_ids = {id(tag) for tag in matched}
    ancestor_ids = {id(p) for tag in matched for p in tag.parents}
    # an element inside another matched one is kept with it
    for tag in matched:
        _clean(tag)

    def prune(node: Tag) -> None:
        for child in list(node.children):
            if isinstance(child, Tag):
                if id(child) in matched_ids:
                    continue
                if id(child) in ancestor_ids:
                    child.attrs = {
                        k: v for k, v in child.attrs.items() if k in _ANCESTOR_ATTRS
                    }
                    prune(child)
                else:
                    child.extract()
            else:
                child.extract()  # text and comments outside the matched elements

    prune(soup)
    head = '<!doctype html>\n<meta charset="utf-8">\n'
    return head + soup.prettify()


def _clean(tag: Tag) -> None:
    """Remove media, scripts, comments and heavy attributes below a kept element."""
    for node in tag.find_all(True):
        if node.name in _DROP_TAGS:
            node.decompose()
    for node in tag.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()
    for node in [tag, *tag.find_all(True)]:
        node.attrs = {k: v for k, v in node.attrs.items() if k not in _DROP_ATTRS}
