"""
Table of Contents Extension for Python-Markdown
===============================================

See <https://pythonhosted.org/Markdown/extensions/toc.html>
for documentation.

Oringinal code Copyright 2008 [Jack Miller](http://codezen.org)

All changes Copyright 2008-2014 The Python Markdown Project

License: [BSD](http://www.opensource.org/licenses/bsd-license.php)

Modified for C2C : remove title emphasis, toc HTML class. Add c2c:role
"""

from markdown.util import code_escape
from markdown.extensions.toc import (TocExtension, TocTreeprocessor,
                                     stashedHTML2text, unescape,
                                     unique, nest_toc_tokens,
                                     AtomicString, html)


def not_emphasis(elt):
    return elt.attrib.get("c2c:role") != "header-emphasis"


def get_name(el):
    """Get title name."""

    result = []
    for item in el.iter():
        if not_emphasis(item):
            text = item.text
            if isinstance(text, AtomicString):
                result.append(html.unescape(text))
            elif text:
                result.append(text)

    return ''.join(result).strip()


class C2CTocTreeprocessor(TocTreeprocessor):
    # ## c2c comment
    #
    # we have to handle two use case:
    #
    # 1. do not add emphasis in ids
    # 2. add a c2c:role attribute, and remove class attribute
    #
    # The TOC extension dos not allow such customization, so we have to hack
    #
    # One solution could have been to copy paste the entire toc extension, and
    # modify what needed. But we would have missed any evolution (or at a
    # higher cost).
    #
    # The solution here is to inherit from base TocTreeprocessor and overwrite
    # run() method. There is two modifications:
    #
    # 1. use a custom get_name() function that filters out emphasis
    # 2. add `div.attrib["c2c:role"] = "toc"` and class deletion

    def run(self, doc):
        # Get a list of id attributes
        used_ids = set()
        for el in doc.iter():
            if "id" in el.attrib:
                used_ids.add(el.attrib["id"])

        toc_tokens = []
        for el in doc.iter():
            if isinstance(el.tag, str) and self.header_rgx.match(el.tag):
                self.set_level(el)
                text = get_name(el)

                # Do not override pre-existing ids
                if "id" not in el.attrib:
                    innertext = unescape(stashedHTML2text(text, self.md))
                    el.attrib["id"] = unique(self.slugify(innertext, self.sep), used_ids)  # noqa: E501

                if int(el.tag[-1]) >= self.toc_top and int(el.tag[-1]) <= self.toc_bottom:  # noqa: E501
                    toc_tokens.append({
                        'level': int(el.tag[-1]),
                        'id': el.attrib["id"],
                        'name': unescape(stashedHTML2text(
                            code_escape(el.attrib.get('data-toc-label', text)),
                            self.md, strip_entities=False
                        ))
                    })

                # Remove the data-toc-label attribute as it is no longer needed
                if 'data-toc-label' in el.attrib:
                    del el.attrib['data-toc-label']

                if self.use_anchors:
                    self.add_anchor(el, el.attrib["id"])
                if self.use_permalinks not in [False, None]:
                    self.add_permalink(el, el.attrib["id"])

        toc_tokens = nest_toc_tokens(toc_tokens)
        div = self.build_toc_div(toc_tokens)
        div.attrib["c2c:role"] = "toc"
        del div.attrib["class"]

        if self.marker:
            self.replace_marker(doc, div)

        # serialize and attach to markdown instance.
        toc = self.md.serializer(div)
        for pp in self.md.postprocessors:
            toc = pp.run(toc)
        self.md.toc_tokens = toc_tokens
        self.md.toc = toc


class C2CTocExtension(TocExtension):
    TreeProcessorClass = C2CTocTreeprocessor


def makeExtension(*args, **kwargs):  # noqa: N802
    return C2CTocExtension(*args, **kwargs)
