"""c2corg wikiLinks extension for Python-Markdown.

Converts tags such as [[document_type/document_id|label]]
to <a href="/document_type/document_id">label</a>

Inspired from https://github.com/waylan/Python-Markdown/blob/master
/markdown/extensions/wikilinks.py
"""

import re
from xml.etree import ElementTree  # nosec

from markdown.extensions import Extension
from markdown.inlinepatterns import Pattern
from markdown.treeprocessors import Treeprocessor

# document_type/document_id(/lang(/slug))(#anchor)

DOCUMENT_RE = r'(?P<document_type>[a-z]+)/(?P<document_id>\d+)'
LANG_SLUG_RE = r'(/(?P<lang>[a-z]{2})(/(?P<slug>[a-z0-9\-]+))?)?'
ANCHOR_RE = r'(#(?P<anchor>[a-z0-9\-_]+))?'
LABEL_RE = r'(?P<label>[^\]]+)'

TARGET_RE = ''.join((DOCUMENT_RE, LANG_SLUG_RE, ANCHOR_RE))

WIKILINK_RE = r'\[\[' + TARGET_RE + r'\|' + LABEL_RE + r'\]\]'

# a link to a document of the site written as a full URL, e.g.
# https://www.camptocamp.org/routes/123/fr/slug (also the v5 types, such as
# /summits/123, which the site redirects)
SITE_URL_RE = re.compile(
    r'^https?://(?:www\.|m\.)?camptocamp\.org/'
    r'(?P<document_type>[a-z]+)/(?P<document_id>\d+)(?:[/?#]|$)',
    re.IGNORECASE,
)


class C2CWikiLinkExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802
        pattern = C2CWikiLinks(WIKILINK_RE)
        # append to end of inline patterns
        md.inlinePatterns.register(pattern, 'c2c_wikilink', 75)
        # after the inline patterns (20): the links are built
        md.treeprocessors.register(C2CLinkCollector(md), 'c2c_link_collector', 1)


class C2CWikiLinks(Pattern):
    def handleMatch(self, m):  # noqa: N802

        a = ElementTree.Element(
            'a',
            {
                'c2c:role': 'internal-link',
                'c2c:document-id': m.group('document_id'),
                'c2c:document-type': m.group('document_type'),
            },
        )

        a.text = m.group('label')

        lang = m.group('lang')
        slug = m.group('slug')
        anchor = m.group('anchor')

        if lang:
            a.set('c2c:lang', lang)

        if anchor:
            a.set('c2c:anchor', anchor)

        if slug:
            a.set('c2c:slug', slug)

        return a


class C2CLinkCollector(Treeprocessor):
    """Collect the links to documents of the site, for get_text_references()."""

    # (document type as written, document id, written as a full URL); only
    # when the parser has a list to fill (`c2c_linked_documents`)
    def run(self, root):
        links = getattr(self.md, 'c2c_linked_documents', None)
        if links is None:
            return
        for a in root.iter('a'):
            if a.get('c2c:role') == 'internal-link':
                links.append(
                    (a.get('c2c:document-type'), int(a.get('c2c:document-id')), False)
                )
                continue
            m = SITE_URL_RE.match(a.get('href') or '')
            if m:
                links.append(
                    (
                        m.group('document_type').lower(),
                        int(m.group('document_id')),
                        True,
                    )
                )


def makeExtension(*args, **kwargs):  # noqa: N802
    return C2CWikiLinkExtension(*args, **kwargs)
