"""
c2corg img Extension for Python-Markdown
==============================================

Converts tags like
[img=<id>(<options>)(/)?](<caption>)?([/img])?
to advanced HTML img tags.
"""

from markdown.extensions import Extension
from markdown.blockprocessors import BlockProcessor
from xml.etree import ElementTree  # nosec

import os
import re

# \w\W pattern is a trick for capturing all, including new spaces
IMG_RE = r'(?:^|\n)\[img=(\d+)([a-z_ ]*)(/\]|\]([\w\W]*?)\[/img\])'

# loose pattern used to collect the ids of embedded images before parsing,
# it may match a bit more than IMG_RE (e.g. in code blocks)
IMG_ID_RE = re.compile(r'\[img=(\d+)')


def get_image_url(base_url, filename, size):
    """Return the media server URL of an image."""
    # built like the redirect of ImageProxyRest.get (views/image.py)
    if not size:
        return base_url + filename
    base, ext = os.path.splitext(filename)
    if ext == '.svg':
        ext = '.jpg'
    return base_url + base + size + ext


def make_image_url_resolver(base_url, filenames):
    """Return a `(document_id, size) -> url or None` for `parse_code()`."""

    # filenames maps image document ids (int) to filenames
    def resolve(document_id, size):
        filename = filenames.get(int(document_id))
        if not filename:
            return None
        return get_image_url(base_url, filename, size)

    return resolve


class C2CImageExtension(Extension):
    def __init__(self, *args, **kwargs):
        """Take an optional `url_secret_attribute` keyword argument."""
        # name of the attribute holding the direct image URL, renamed to
        # c2c:url after sanitizing (see c2corg_api.markdown.parse_code)
        self._url_secret_attribute = kwargs.pop('url_secret_attribute', 'c2c:url')
        super().__init__(*args, **kwargs)

    def extendMarkdown(self, md):  # noqa: N802
        self.md = md
        md.parser.blockprocessors.register(
            C2CImageBlock(md.parser, self.getConfigs(), self._url_secret_attribute),
            'c2c_imgblock',
            15,
        )


class C2CImageBlock(BlockProcessor):
    RE = re.compile(IMG_RE)

    def __init__(self, parser, config, url_secret_attribute):
        """Build the processor, see `C2CImageExtension.__init__`."""
        super().__init__(parser)
        self.config = config
        self._url_secret_attribute = url_secret_attribute

    def test(self, parent, block):
        return bool(self.RE.search(block))

    def run(self, parent, blocks):
        block = blocks.pop(0)
        m = self.RE.search(block)

        before = block[: m.start()]
        self.parser.parseBlocks(parent, [before])

        parent.append(self.build_element(m))

        after = block[m.end() :]
        self.parser.parseBlocks(parent, [after])

    def build_element(self, m):
        # group(1) is everything before the pattern
        # group(2) is the first group of the pattern
        img_id = m.group(1)
        options = m.group(2).split() if m.group(2) else []
        caption = m.group(4).strip() if m.group(4) else ''

        position = 'inline'
        img_size = 'MI'
        for option in options:
            if option in ['left', 'right', 'center', 'inline']:
                position = option
            elif option == 'big':
                img_size = 'BI'
            elif option == 'small':
                img_size = 'SI'
            elif option == 'orig':
                img_size = ''

        img = ElementTree.Element('img')

        img_url = '/images/proxy/%s' % (img_id,)

        if img_size:
            img_url += '?size=' + img_size

        img.set('alt', (caption or img_id).replace('\n', ' '))
        img.set('c2c:url-proxy', img_url)

        # direct URL to the media server, when the image is known. Clients
        # should prefer it to c2c:url-proxy, which costs one API request.
        resolve = getattr(self.parser.md, 'c2c_image_url_resolver', None)
        direct_url = resolve(img_id, img_size) if resolve else None
        if direct_url:
            img.set(self._url_secret_attribute, direct_url)
        img.set('c2c:role', 'embedded-image')
        img.set('c2c:document-id', img_id)
        img.set('c2c:size', img_size)

        fig = ElementTree.Element('figure')

        fig.append(img)
        fig.set('c2c:position', position)
        fig.set('c2c:role', 'embedded-figure')
        fig.set('c2c:size', img_size)

        if caption:
            img_caption = ElementTree.Element('figcaption')
            img_caption.text = caption
            fig.append(img_caption)

        return fig


def makeExtension(*args, **kwargs):  # noqa: N802
    return C2CImageExtension(*args, **kwargs)
