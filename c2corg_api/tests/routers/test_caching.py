"""
FastAPI caching tests.

Tests ETag headers and dogpile.cache behaviour for every document
type that has detail, info and version endpoints on the ``/v2/``
FastAPI router.

Each concrete test class inherits 15 sub-tests from
``CachingTestMixin`` and only needs to supply test data
(``_add_test_data``), the URL prefix (``_prefix``) and the
document-type constant (``_doc_type``).

Doc types tested:
  book, waypoint, route, outing, xreport, topo_map, area, article, image
"""

from datetime import date

from dogpile.cache.api import NO_VALUE
from fastapi.testclient import TestClient

from c2corg_api.caching import (
    cache_document_detail,
    cache_document_info,
    cache_document_version,
)
from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE, Area
from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.models.book import BOOK_TYPE, Book
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.xreport import XREPORT_TYPE, Xreport, XreportLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version

# =====================================================================
# Mixin — parameterised ETag + dogpile sub-tests
# =====================================================================


class CachingTestMixin:
    """Mixin providing 15 caching / ETag sub-tests.

    Concrete test classes must define:
    * ``_doc_type``   — e.g. ``WAYPOINT_TYPE``
    * ``_doc``        — the SA model instance (set in ``_add_test_data``)
    * ``_version``    — the ``DocumentVersion`` row  (set in ``_add_test_data``)
    * ``_prefix``     — URL prefix, e.g. ``'/v2/waypoints'``
    """

    _doc_type: str
    _prefix: str

    def _detail_url(self):
        return f'{self._prefix}/{self._doc.document_id}'

    def _info_url(self, lang='en'):
        return f'{self._prefix}/{self._doc.document_id}/{lang}/info'

    def _version_url(self):
        return f'{self._prefix}/{self._doc.document_id}/en/{self._version.id}'

    # ── version ETag ─────────────────────────────────────────

    def test_version_etag_is_set(self):
        resp = self.client.get(self._version_url())
        assert resp.status_code == 200
        etag = resp.headers.get('etag')
        assert etag is not None
        assert etag.startswith('W/"')

    def test_version_etag_304(self):
        resp = self.client.get(self._version_url())
        assert resp.status_code == 200
        etag = resp.headers['etag']
        resp2 = self.client.get(self._version_url(), headers={'If-None-Match': etag})
        assert resp2.status_code == 304

    def test_version_etag_stale(self):
        resp = self.client.get(
            self._version_url(), headers={'If-None-Match': 'W/"stale-etag"'}
        )
        assert resp.status_code == 200
        assert resp.headers.get('etag') is not None

    # ── version dogpile cache ────────────────────────────────

    def test_version_populates_cache(self):
        cache_key = '{}-{}'.format(
            get_cache_key(self._doc.document_id, 'en', self._doc_type, db=self.session), self._version.id
        )
        assert cache_document_version.get(cache_key) == NO_VALUE
        resp = self.client.get(self._version_url())
        assert resp.status_code == 200
        assert cache_document_version.get(cache_key) != NO_VALUE

    def test_version_serves_from_cache(self):
        cache_key = '{}-{}'.format(
            get_cache_key(self._doc.document_id, 'en', self._doc_type, db=self.session), self._version.id
        )
        resp = self.client.get(self._version_url())
        assert resp.status_code == 200

        fake = {'document': 'fastapi-cached'}
        cache_document_version.set(cache_key, fake)

        resp = self.client.get(self._version_url())
        assert resp.status_code == 200
        assert resp.json() == fake

    # ── info ETag ────────────────────────────────────────────

    def test_info_etag_is_set(self):
        resp = self.client.get(self._info_url())
        assert resp.status_code == 200
        assert resp.headers.get('etag') is not None

    def test_info_etag_304(self):
        resp = self.client.get(self._info_url())
        assert resp.status_code == 200
        etag = resp.headers['etag']
        resp2 = self.client.get(self._info_url(), headers={'If-None-Match': etag})
        assert resp2.status_code == 304

    # ── info dogpile cache ───────────────────────────────────

    def test_info_populates_cache(self):
        cache_key = get_cache_key(self._doc.document_id, 'en', self._doc_type, db=self.session)
        assert cache_document_info.get(cache_key) == NO_VALUE
        resp = self.client.get(self._info_url())
        assert resp.status_code == 200
        assert cache_document_info.get(cache_key) != NO_VALUE

    def test_info_serves_from_cache(self):
        cache_key = get_cache_key(self._doc.document_id, 'en', self._doc_type, db=self.session)
        resp = self.client.get(self._info_url())
        assert resp.status_code == 200

        fake = {'document_id': 999, 'locales': [{'lang': 'en'}]}
        cache_document_info.set(cache_key, fake)
        resp = self.client.get(self._info_url())
        assert resp.status_code == 200
        assert resp.json() == fake

    # ── detail ETag ──────────────────────────────────────────

    def test_detail_etag_is_set(self):
        resp = self.client.get(self._detail_url())
        assert resp.status_code == 200
        assert resp.headers.get('etag') is not None

    def test_detail_etag_304(self):
        resp = self.client.get(self._detail_url())
        assert resp.status_code == 200
        etag = resp.headers['etag']
        resp2 = self.client.get(self._detail_url(), headers={'If-None-Match': etag})
        assert resp2.status_code == 304

    # ── detail dogpile cache ─────────────────────────────────

    def test_detail_populates_cache(self):
        cache_key = get_cache_key(self._doc.document_id, None, self._doc_type, db=self.session)
        assert cache_document_detail.get(cache_key) == NO_VALUE
        resp = self.client.get(self._detail_url())
        assert resp.status_code == 200
        assert cache_document_detail.get(cache_key) != NO_VALUE

    def test_detail_serves_from_cache(self):
        cache_key = get_cache_key(self._doc.document_id, None, self._doc_type, db=self.session)
        assert cache_document_detail.get(cache_key) == NO_VALUE

        resp1 = self.client.get(self._detail_url())
        assert resp1.status_code == 200
        body1 = resp1.json()

        cached = cache_document_detail.get(cache_key)
        assert cached != NO_VALUE

        resp2 = self.client.get(self._detail_url())
        assert resp2.status_code == 200
        assert body1['document_id'] == resp2.json()['document_id']

    # ── editing view bypasses cache ──────────────────────────

    def test_detail_editing_view_bypasses_cache(self):
        cache_key = get_cache_key(self._doc.document_id, None, self._doc_type, db=self.session)
        fake = {'document': 'should-not-be-returned'}
        cache_document_detail.set(cache_key, fake)

        resp = self.client.get(f'{self._detail_url()}?e=1')
        assert resp.status_code == 200
        assert resp.json() != fake

    def test_detail_editing_view_no_etag(self):
        resp = self.client.get(f'{self._detail_url()}?e=1')
        assert resp.status_code == 200
        assert resp.headers.get('etag') is None


# =====================================================================
# Base class — shared setUp / tearDown
# =====================================================================


class _CachingTestBase(BaseTestCase):
    """Common setUp / tearDown for all caching test classes."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _create_version(self, doc):
        user_id = global_userids['contributor']
        create_new_version(doc, user_id, db=self.session)
        self.session.expire_all()
        return (
            self.session.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.document_id,
                DocumentVersion.lang == 'en',
            )
            .first()
        )


# =====================================================================
# Book
# =====================================================================


class TestBookCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = BOOK_TYPE
    _prefix = '/v2/books'

    def _add_test_data(self):
        self._doc = Book(activities=['hiking'], book_types=['biography'])
        self._doc.locales.append(
            DocumentLocale(lang='en', title='Escalades au Thaurac')
        )
        self._doc.locales.append(
            DocumentLocale(lang='fr', title='Escalades au Thaurac')
        )
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Waypoint
# =====================================================================


class TestWaypointCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = WAYPOINT_TYPE
    _prefix = '/v2/waypoints'

    def _add_test_data(self):
        self._doc = Waypoint(waypoint_type='summit', elevation=2203)
        self._doc.locales.append(DocumentLocale(lang='en', title='Mont Blanc'))
        self._doc.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Route
# =====================================================================


class TestRouteCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = ROUTE_TYPE
    _prefix = '/v2/routes'

    def _add_test_data(self):
        wp = Waypoint(waypoint_type='summit', elevation=4000)
        wp.locales.append(DocumentLocale(lang='en', title='WP'))
        wp.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(wp)
        self.session.flush()

        self._doc = Route(activities=['skitouring'], main_waypoint_id=wp.document_id)
        self._doc.locales.append(DocumentLocale(lang='en', title='Voie Normale'))
        self._doc.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Outing
# =====================================================================


class TestOutingCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = OUTING_TYPE
    _prefix = '/v2/outings'

    def _add_test_data(self):
        self._doc = Outing(
            activities=['skitouring'],
            date_start=date(2020, 1, 1),
            date_end=date(2020, 1, 1),
        )
        self._doc.locales.append(OutingLocale(lang='en', title='Sortie au Mont Blanc'))
        self._doc.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Xreport
# =====================================================================


class TestXreportCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = XREPORT_TYPE
    _prefix = '/v2/xreports'

    def _add_test_data(self):
        self._doc = Xreport(
            event_activity='skitouring',
            event_type='stone_ice_fall',
            date=date(2020, 1, 1),
        )
        self._doc.locales.append(XreportLocale(lang='en', title='Incident report'))
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Topo Map
# =====================================================================


class TestTopoMapCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = MAP_TYPE
    _prefix = '/v2/maps'

    def _add_test_data(self):
        self._doc = TopoMap(editor='IGN', scale='25000', code='3431OT')
        self._doc.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self._doc.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)',
            geom_detail=(
                'SRID=3857;POLYGON((635900 5723500, 636000 5723500, '
                '636000 5723700, 635900 5723700, 635900 5723500))'
            ),
        )
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Area
# =====================================================================


class TestAreaCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = AREA_TYPE
    _prefix = '/v2/areas'

    def _add_test_data(self):
        self._doc = Area(area_type='range')
        self._doc.locales.append(
            DocumentLocale(lang='en', title='Massif du Mont-Blanc')
        )
        self._doc.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)',
            geom_detail=(
                'SRID=3857;POLYGON((635900 5723500, 636000 5723500, '
                '636000 5723700, 635900 5723700, 635900 5723500))'
            ),
        )
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Article
# =====================================================================


class TestArticleCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = ARTICLE_TYPE
    _prefix = '/v2/articles'

    def _add_test_data(self):
        self._doc = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self._doc.locales.append(DocumentLocale(lang='en', title='How to hike safely'))
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)


# =====================================================================
# Image
# =====================================================================


class TestImageCaching(CachingTestMixin, _CachingTestBase):
    _doc_type = IMAGE_TYPE
    _prefix = '/v2/images'

    def _add_test_data(self):
        self._doc = Image(
            filename='test_cache.jpg',
            activities=['hiking'],
            height=500,
            image_type='collaborative',
        )
        self._doc.locales.append(DocumentLocale(lang='en', title='Beautiful view'))
        self._doc.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self._doc)
        self.session.flush()
        self._version = self._create_version(self._doc)
