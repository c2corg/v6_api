import markdown
from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension

import c2corg_api.markdown as c2c_markdown


class FailingProcessor(BlockProcessor):
    def test(self, parent, block):
        return True

    def run(self, parent, blocks):
        raise Exception('I should be invisible')


class FailingExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802
        md.parser.blockprocessors.register(
            FailingProcessor(md.parser), 'c2c_failing', 10.0001
        )


def fake_get_markdown_parser(*args, **kwargs):
    return markdown.Markdown(
        output_format='xhtml5', extensions=[FailingExtension()], enable_attributes=False
    )


def test_exception(monkeypatch):
    # parse_code() should never raise an exception: the parsing and the
    # cleaning are in a try block. If an extension raises, the default
    # message (_PARSER_EXCEPTION_MESSAGE) is returned.
    monkeypatch.setattr(c2c_markdown, '_get_markdown_parser', fake_get_markdown_parser)
    result = c2c_markdown.parse_code('!! Hello')
    assert result == c2c_markdown._PARSER_EXCEPTION_MESSAGE
