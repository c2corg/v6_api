import unittest
import markdown
from markdown.extensions import Extension
from markdown.blockprocessors import BlockProcessor

import c2corg_api.markdown as c2c_markdown


class FailingProcessor(BlockProcessor):
    def test(self, parent, block):
        return True

    def run(self, parent, blocks):
        raise Exception("I should be invisible")


class FailingExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802
        md.parser.blockprocessors.register(
            FailingProcessor(md.parser),
            'c2c_failing',
            10.0001
        )


def fake_get_markdown_parser(*args, **kwargs):
    return markdown.Markdown(output_format='xhtml5',
                             extensions=[FailingExtension()],
                             enable_attributes=False)


class TestFormat(unittest.TestCase):
    """
    parse_code() function should never raise an exception. All sensitive
    functions (parsing and cleaning) are inside a try-catch block. This
    test-case verifies that, if some extension raises an exception, the
    appropriate default message (_PARSER_EXCEPTION_MESSAGE) is returned.
    """
    def setUp(self):
        self.real_get_markdown_parser = c2c_markdown._get_markdown_parser
        c2c_markdown._get_markdown_parser = fake_get_markdown_parser

    def test_exception(self):
        result = c2c_markdown.parse_code("!! Hello")
        self.assertEqual(result, c2c_markdown._PARSER_EXCEPTION_MESSAGE)

    def tearDown(self):
        c2c_markdown._get_markdown_parser = self.real_get_markdown_parser
