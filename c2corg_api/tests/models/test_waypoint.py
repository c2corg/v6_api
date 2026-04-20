import json

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import StaleDataError

from c2corg_api.models.document import DocumentGeometry, UpdateType, set_available_langs
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import BaseTestCase


class TestWaypoint(BaseTestCase):
    def test_inheritance(self):
        waypoint = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[WaypointLocale(lang='en', title='A', description='abc')],
            geometry=DocumentGeometry(geom=from_shape(Point(1, 1), srid=3857)),
        )
        self.session.add(waypoint)
        self.session.flush()

        assert waypoint.document_id is not None
        assert 'w' == waypoint.type

        locale = waypoint.locales[0]
        assert locale.id is not None
        assert 'w' == locale.type

    def test_to_archive(self):
        waypoint = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=2203,
            locales=[
                WaypointLocale(id=2, lang='en', title='A', description='abc'),
                WaypointLocale(id=3, lang='fr', title='B', description='bcd'),
            ],
            geometry=DocumentGeometry(
                document_id=1, geom=from_shape(Point(1, 1), srid=3857)
            ),
        )

        waypoint_archive = waypoint.to_archive()

        assert waypoint_archive.id is None
        assert waypoint_archive.document_id == waypoint.document_id
        assert waypoint_archive.waypoint_type == waypoint.waypoint_type
        assert waypoint_archive.elevation == waypoint.elevation

        archive_locals = waypoint.get_archive_locales()

        assert len(archive_locals) == 2
        locale = waypoint.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
        assert locale_archive.description == locale.description

        archive_geometry = waypoint.get_archive_geometry()
        assert archive_geometry.id is None
        assert archive_geometry.document_id is not None
        assert archive_geometry.document_id == waypoint.document_id
        assert archive_geometry.geom is not None

    def test_version_is_incremented(self):
        waypoint = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[WaypointLocale(lang='en', title='A', description='abc')],
        )
        self.session.add(waypoint)
        self.session.flush()

        version1 = waypoint.version
        assert version1 is not None

        # make a change to the waypoint and check that the version changes
        # once the waypoint is persisted
        waypoint.elevation = 1234
        self.session.merge(waypoint)
        self.session.flush()
        version2 = waypoint.version
        assert version1 != version2

    def test_version_concurrent_edit(self):
        """Test that a `StaleDataError` is thrown when trying to update a
        waypoint with an old version number.
        """
        waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[WaypointLocale(lang='en', title='A', description='abc')],
        )

        # add the initial waypoint
        self.session.add(waypoint1)
        self.session.flush()
        self.session.expunge(waypoint1)
        version1 = waypoint1.version
        assert version1 is not None

        # change the waypoint
        waypoint2 = self.session.get(Waypoint, waypoint1.document_id)
        waypoint2.elevation = 1234
        self.session.merge(waypoint2)
        self.session.flush()
        version2 = waypoint2.version
        assert version1 != version2

        assert waypoint1.version != waypoint2.version
        assert waypoint1.elevation != waypoint2.elevation

        # then try to update the waypoint again with the old version
        waypoint1.elevation = 2345
        pytest.raises(StaleDataError, self.session.merge, waypoint1)

    def test_geometry_update_optimization_4326(self):
        lat = 46.0
        geom1 = 'SRID=4326;POINT(' + str(lat) + ' 6.0)'
        waypoint_db = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=2203,
            geometry=DocumentGeometry(document_id=1, geom=geom1),
        )

        # ~0.5m shift: should be within tolerance (~1m), no update
        waypoint_in = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=1234,
            geometry=DocumentGeometry(
                geom='SRID=4326;POINT(' + str(lat + 5e-6) + ' 6.0)'
            ),
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.geometry.geom == geom1

        # ~2m shift: should exceed tolerance (~1m), triggers update
        waypoint_in = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=1234,
            geometry=DocumentGeometry(
                geom='SRID=4326;POINT(' + str(lat + 2e-5) + ' 6.0)'
            ),
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.geometry.geom != geom1

    def test_geometry_update_optimization_3857(self):
        geom1 = 'SRID=3857;POINT(445278.0 1.0)'
        waypoint_db = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=2203,
            geometry=DocumentGeometry(document_id=1, geom=geom1),
        )

        waypoint_in = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=1234,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(445278.5 1.0)'),
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.geometry.geom == geom1

        waypoint_in = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=14,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(445279.0 1.0)'),
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.geometry.geom != geom1

    def test_geometry_update_skip_optimization(self):
        geom1 = 'SRID=3857;POINT(445278.0 334111.0)'
        waypoint_db = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=2203,
            geometry=DocumentGeometry(document_id=1, geom=geom1),
        )

        waypoint_in = Waypoint(
            document_id=1, waypoint_type='summit', elevation=1234, geometry=None
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.geometry.geom == geom1

    def test_update(self):
        waypoint_db = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=2203,
            version=123,
            locales=[
                WaypointLocale(
                    id=2, lang='en', title='A', description='abc', version=345
                ),
                WaypointLocale(
                    id=3, lang='fr', title='B', description='bcd', version=678
                ),
            ],
            geometry=DocumentGeometry(document_id=1, geom='SRID=3857;POINT(1 2)'),
        )
        waypoint_in = Waypoint(
            document_id=1,
            waypoint_type='summit',
            elevation=1234,
            version=123,
            locales=[
                WaypointLocale(
                    id=2, lang='en', title='C', description='abc', version=345
                ),
                WaypointLocale(lang='es', title='D', description='efg'),
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(3 4)'),
        )
        waypoint_db.update(waypoint_in)
        assert waypoint_db.elevation == waypoint_in.elevation
        assert len(waypoint_db.locales) == 3

        locale_en = waypoint_db.get_locale('en')
        locale_fr = waypoint_db.get_locale('fr')
        locale_es = waypoint_db.get_locale('es')

        assert locale_en.title == 'C'
        assert locale_fr.title == 'B'
        assert locale_es.title == 'D'

        assert waypoint_db.geometry.geom == 'SRID=3857;POINT(3 4)'

    def test_get_update_type_figures_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.elevation = 1234
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert UpdateType.FIGURES in types
        assert changed_langs == []

    def test_get_update_type_geom_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.geometry.geom = 'SRID=3857;POINT(3 4)'
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert UpdateType.GEOM in types
        assert changed_langs == []

    def test_get_update_type_lang_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.get_locale('en').description = 'abcd'
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert UpdateType.LANG in types
        assert changed_langs == ['en']

    def test_get_update_type_lang_only_new_lang(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.locales.append(WaypointLocale(lang='es', title='A', description='abc'))
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert UpdateType.LANG in types
        assert changed_langs == ['es']

    def test_get_update_type_all(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.elevation = 1234
        waypoint.get_locale('en').description = 'abcd'
        waypoint.locales.append(WaypointLocale(lang='es', title='A', description='abc'))

        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert UpdateType.LANG in types
        assert UpdateType.FIGURES in types
        assert UpdateType.GEOM not in types
        assert changed_langs == ['en', 'es']

    def test_get_update_type_none(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        assert types == []
        assert changed_langs == []

    def test_save_geometry(self):
        waypoint = self._get_waypoint()
        waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956.075332665 5723604.677994)'
        )
        self.session.add(waypoint)
        self.session.flush()

    def test_get_geometry_lon_lat(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()
        self.session.expire(waypoint)

        waypoint = (
            self.session.query(Waypoint)
            .options(joinedload(Waypoint.geometry).load_only(DocumentGeometry.lon_lat))
            .filter(Waypoint.document_id == waypoint.document_id)
            .first()
        )

        lon_lat_geojson = json.loads(waypoint.geometry.lon_lat)
        assert lon_lat_geojson['coordinates'][0] == pytest.approx(5.7128906, abs=1e-06)
        assert lon_lat_geojson['coordinates'][1] == pytest.approx(45.644768, abs=1e-06)

    def test_get_geometry_lon_lat_none(self):
        waypoint = self._get_waypoint()
        waypoint.geometry = None
        self.session.add(waypoint)
        self.session.flush()
        self.session.expire(waypoint)

        waypoint = (
            self.session.query(Waypoint)
            .options(joinedload(Waypoint.geometry).load_only(DocumentGeometry.lon_lat))
            .filter(Waypoint.document_id == waypoint.document_id)
            .first()
        )

        assert waypoint.geometry is None

    def test_set_available_langs(self):
        waypoint = self._get_waypoint()
        waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956.075332665 5723604.677994)'
        )
        self.session.add(waypoint)
        self.session.flush()

        set_available_langs([waypoint])
        assert set(waypoint.available_langs) == set(['en', 'fr'])

    def test_array_handling_non_empty(self):
        waypoint = Waypoint(
            waypoint_type='summit', elevation=2203, rock_types=['basalte']
        )
        self.session.add(waypoint)
        self.session.flush()

        self.session.refresh(waypoint)
        assert waypoint.rock_types == ['basalte']

    def test_array_handling_empty(self):
        waypoint = Waypoint(waypoint_type='summit', elevation=2203, rock_types=[])
        self.session.add(waypoint)
        self.session.flush()

        self.session.refresh(waypoint)
        assert waypoint.rock_types == []

    def test_array_handling_none(self):
        waypoint = Waypoint(waypoint_type='summit', elevation=2203, rock_types=None)
        self.session.add(waypoint)
        self.session.flush()

        self.session.refresh(waypoint)
        assert waypoint.rock_types is None

    def test_archive_unique_version_document_id(self):
        """Tests that there can be only one entry for each version of a
        document.
        """
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        archive = waypoint.to_archive()
        self.session.add(archive)
        self.session.flush()

        # to try add an archive with the same version
        archive = waypoint.to_archive()
        with pytest.raises(IntegrityError):
            self.session.add(archive)
            self.session.flush()

    def test_locale_archive_unique_version_document_id(self):
        """Tests that there can be only one entry for each version and lang
        of a document locale.
        """
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        locale = waypoint.get_locale('en')
        archive = locale.to_archive()
        self.session.add(archive)
        self.session.flush()

        # to try add an archive with the same version
        archive = locale.to_archive()
        with pytest.raises(IntegrityError):
            self.session.add(archive)
            self.session.flush()

    def test_geometry_unique_version_document_id(self):
        """Tests that there can be only one entry for each version of a
        document geometry.
        """
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        geometry = waypoint.geometry
        archive = geometry.to_archive()
        self.session.add(archive)
        self.session.flush()

        # to try add an archive with the same version
        archive = geometry.to_archive()
        with pytest.raises(IntegrityError):
            self.session.add(archive)
            self.session.flush()

    def test_set_local_external_resource(self):
        en_external_resources = 'https://wikipedia.com/en'
        fr_external_resources = 'https://wikipedia.com/fr'
        waypoint = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[
                WaypointLocale(
                    lang='en',
                    title='English',
                    description='abc',
                    access='y',
                    external_resources=en_external_resources,
                ),
                WaypointLocale(
                    lang='fr',
                    title='French',
                    description='bcd',
                    access='y',
                    external_resources=fr_external_resources,
                ),
            ],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956.075332665 5723604.677994)'
            ),
        )
        self.session.add(waypoint)
        self.session.flush()
        self.session.refresh(waypoint)
        fr_local = [local for local in waypoint.locales if local.title == 'French'][0]
        en_local = [local for local in waypoint.locales if local.title == 'English'][0]
        assert en_local.external_resources == en_external_resources
        assert fr_local.external_resources == fr_external_resources

    def _get_waypoint(self):
        return Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[
                WaypointLocale(lang='en', title='A', description='abc', access='y'),
                WaypointLocale(lang='fr', title='B', description='bcd', access='y'),
            ],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956.075332665 5723604.677994)'
            ),
        )
