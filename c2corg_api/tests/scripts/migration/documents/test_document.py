import unittest

from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class DocumentTest(unittest.TestCase):

    def test_extract_summary(self):
        d = MigrateDocuments(None, None, None)

        text, summary = d.extract_summary(
            '... [abstract][b]the abstract[/b][/abstract] abc')
        self.assertEqual(text, '...  abc')
        self.assertEqual(summary, '[b]the abstract[/b]')

        text, summary = d.extract_summary(
            '... [abs]the abstract[/abs] abc')
        self.assertEqual(text, '...  abc')
        self.assertEqual(summary, 'the abstract')

        text, summary = d.extract_summary(
            '... [abs]the abstract\nmultiline[/abs] abc')
        self.assertEqual(text, '...  abc')
        self.assertEqual(summary, 'the abstract\nmultiline')

        # if there is more than one abstract, only the first is extracted
        # (currently there is no document locale with two abstracts)
        text, summary = d.extract_summary(
            '... [abs]the abstract[/abs] abc'
            '[abs]2nd abstract[/abs]')
        self.assertEqual(text, '...  abc')
        self.assertEqual(summary, 'the abstract')

        text, summary = d.extract_summary(
            '... [b]not the abstract[/b] abc')
        self.assertEqual(text, '... [b]not the abstract[/b] abc')
        self.assertEqual(summary, None)

    def test_convert_tags(self):
        d = MigrateDocuments(None, None, None)

        text = d.convert_q_tags(
            '... [q][b]some whatever[/b] content[/q] abc')
        self.assertEqual(
            text, '... [quote][b]some whatever[/b] content[/quote] abc')

        text = d.convert_c_tags(
            '... [c][b]some whatever[/b] content[/c] abc')
        self.assertEqual(
            text, '... [code][b]some whatever[/b] content[/code] abc')

        text = d.convert_tags(
            '... [[users/123456/fr|Toto le héros]] et ses copains')
        self.assertEqual(
            text, '... [[profiles/123456/fr|Toto le héros]] et ses copains')

        text = """
            Some text with [q]quotes[/q] and [c]code[/c] tags and
            also [b]wikilinks[/b] such as [[users/12345/fr|Toto le héros]]
            and [[summits|summits]] or [[huts/2345|some hut]].
            [q]Pretty cool, isn't it[/q]?
            """
        new_text = """
            Some text with [quote]quotes[/quote] and [code]code[/code] tags and
            also [b]wikilinks[/b] such as [[profiles/12345/fr|Toto le héros]]
            and [[waypoints|summits]] or [[waypoints/2345|some hut]].
            [quote]Pretty cool, isn't it[/quote]?
            """
        self.assertEqual(new_text, d.convert_tags(text))
