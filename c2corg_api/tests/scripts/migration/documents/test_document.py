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
