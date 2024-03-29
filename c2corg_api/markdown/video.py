'''
c2corg video Extension for Python-Markdown
==============================================

Converts video tags to advanced HTML video tags.
'''

from markdown.extensions import Extension
from markdown.blockprocessors import BlockProcessor
from xml.etree import ElementTree  # nosec
import re


class C2CVideoExtension(Extension):
    def __init__(self, *args, **kwargs):
        self._iframe_secret_tag = kwargs.pop("iframe_secret_tag")
        super(C2CVideoExtension, self).__init__(*args, **kwargs)

    def extendMarkdown(self, md):  # noqa: N802

        processors = md.parser.blockprocessors

        for processor, priority in (
            (C2CYoutubeVideoBlock, 14),
            (C2CYoutubeShortVideoBlock, 13),
            (C2CDailymotionVideoBlock, 12),
            (C2CDailymotionShortVideoBlock, 11),
            (C2CVimeoVideoBlock, 10.5)
        ):
            processors.register(
                processor(md.parser, self._iframe_secret_tag),
                processor.__name__,
                priority
            )


class C2CVideoBlock(BlockProcessor):
    PATTERN = None

    def __init__(self, parser, iframe_secret_tag):
        super(C2CVideoBlock, self).__init__(parser=parser)
        self._iframe_secret_tag = iframe_secret_tag
        self.RE = re.compile(r"(^|\n)\[video\]" +
                             self.PATTERN +
                             r"\[/video\]")

    def test(self, parent, block):
        return bool(self.RE.search(block))

    def run(self, parent, blocks):
        block = blocks.pop(0)
        m = self.RE.search(block)

        before = block[:m.start()]
        self.parser.parseBlocks(parent, [before])

        parent.append(self.build_element(m))

        after = block[m.end():]
        self.parser.parseBlocks(parent, [after])

    def build_element(self, m):
        raise NotImplementedError()

    def _embed(self, link):
        iframe = ElementTree.Element(self._iframe_secret_tag)
        iframe.set('src', link)
        embed = ElementTree.Element('div')
        embed.set('c2c:role', 'video')
        embed.append(iframe)
        return embed


class C2CYoutubeVideoBlock(C2CVideoBlock):
    PATTERN = (r"https?:\/\/(?:www\.)?youtube\.com"
               r"/watch\?(?:[=&\w]+&)?v=([-\w]+)(?:&.+)?(?:\#.*)?")

    def build_element(self, m):
        return self._embed('//www.youtube.com/embed/' + m.group(2))


class C2CYoutubeShortVideoBlock(C2CYoutubeVideoBlock):
    PATTERN = r"https?:\/\/(?:www\.)?youtu\.be/([-\w]+)(?:\#.*)?"


class C2CDailymotionVideoBlock(C2CVideoBlock):
    PATTERN = (r"https?://(?:www\.)?dailymotion\.com"
               r"/video/([\da-zA-Z]+)_[-&;\w]+(?:\#.*)?")

    def build_element(self, m):
        return self._embed('//www.dailymotion.com/embed/video/' +
                           m.group(2) +
                           '?theme=none&wmode=transparent')


class C2CDailymotionShortVideoBlock(C2CDailymotionVideoBlock):
    PATTERN = r"https?://(?:www\.)?dai\.ly/([\da-zA-Z]+)"


class C2CVimeoVideoBlock(C2CVideoBlock):
    PATTERN = r'https?://(?:www\.)?vimeo\.com/(\d+)(?:\#.*)?'

    def build_element(self, m):
        return self._embed('//player.vimeo.com/video/' +
                           m.group(2) +
                           '?title=0&byline=0' +
                           '&portrait=0&color=ff9933')


def makeExtension(*args, **kwargs):  # noqa: N802
    return C2CVideoExtension(*args, **kwargs)
