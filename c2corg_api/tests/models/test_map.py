from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.topo_map import TopoMap, get_maps
from c2corg_api.models.waypoint import Waypoint

from c2corg_api.tests import BaseTestCase


class TestMap(BaseTestCase):

    def test_to_archive(self):
        m = TopoMap(
            document_id=1, editor='ign', scale='20000', code='3431OT',
            locales=[
                DocumentLocale(
                    id=2, culture='en', title='Lac d\'Annecy'),
                DocumentLocale(
                    id=3, culture='fr', title='Lac d\'Annecy'),
            ]
        )

        map_archive = m.to_archive()

        self.assertIsNone(map_archive.id)
        self.assertEqual(map_archive.document_id, m.document_id)
        self.assertEqual(
            map_archive.editor, m.editor)
        self.assertEqual(map_archive.scale, m.scale)
        self.assertEqual(map_archive.code, m.code)

        archive_locals = m.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = m.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.culture, locale.culture)
        self.assertEqual(locale_archive.title, locale.title)

    def test_get_maps(self):
        map1 = TopoMap(
            locales=[
                DocumentLocale(culture='en', title='Passo del Maloja'),
                DocumentLocale(culture='fr', title='Passo del Maloja')
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POLYGON((1060345.67641127 5869598.161661,1161884.8271513 5866294.47946546,1159243.3608776 5796747.98963817,1058506.68785187 5800000.03655724,1060345.67641127 5869598.161661))')  # noqa
        )
        map2 = TopoMap(
            locales=[
                DocumentLocale(culture='fr', title='Monte Disgrazia')
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POLYGON((1059422.5474971 5834730.45170096,1110000.12573506 5833238.36363707,1108884.30979916 5798519.62445622,1058506.68785187 5800000.03655724,1059422.5474971 5834730.45170096))')  # noqa
        )
        map3 = TopoMap(
            locales=[
                DocumentLocale(culture='fr', title='Sciora')
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POLYGON((1059422.5474971 5834730.45170096,1084713.47958582 5834021.11961652,1084204.54539729 5816641.60293193,1058963.71520182 5817348.14989301,1059422.5474971 5834730.45170096))')  # noqa
        )
        map4 = TopoMap(
            locales=[
                DocumentLocale(culture='fr', title='...')
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POLYGON((753678.422528324 6084684.82967302,857818.351438369 6084952.58494753,857577.289072432 6013614.93425228,754282.556732048 6013351.52692378,753678.422528324 6084684.82967302))')  # noqa
        )
        waypoint = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(geom='SRID=3857;POINT(1069913.22199537 5830556.39234855)')  # noqa
        )
        self.session.add_all([waypoint, map1, map2, map3, map4])
        self.session.flush()

        maps = get_maps(waypoint, 'en')
        self.assertEqual(
            set([m.document_id for m in maps]),
            set([map1.document_id, map2.document_id, map3.document_id]))

        for m in maps:
            # check that the "best" locale is set
            self.assertEqual(len(m.locales), 1)
