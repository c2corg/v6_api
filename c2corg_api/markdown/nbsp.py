from markdown import Extension
from markdown.inlinepatterns import Pattern


class NbspPattern(Pattern):
    HTML_ENTITY = "&nbsp;"

    def handleMatch(self, m):  # noqa: N802
        placeholder = self.md.htmlStash.store(self.HTML_ENTITY)

        return m.group(2).replace(" ", placeholder)


class NarrowNbspPattern(NbspPattern):
    HTML_ENTITY = "&#8239;"


class C2CNbspExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802

        """
        patterns like

            123 m
            coucou :

        must have a non-breakable space instead of a space.
        """
        md.inlinePatterns.register(
                              NbspPattern(r'(\d [a-z]| :)', md),
                              'c2c_nbsp',
                              7)

        md.inlinePatterns.register(
                              NarrowNbspPattern(r'([\w\d] [;?!])', md),
                              'c2c_nnbsp',
                              8)


def makeExtension(*args, **kwargs):  # noqa: N802
    return C2CNbspExtension(*args, **kwargs)
