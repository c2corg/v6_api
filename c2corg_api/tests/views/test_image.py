from c2corg_api.models.image import Image, ImageLocale

from .. import BaseTestCase


class TestImageRest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        response = self.app.get('/images')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIsInstance(body, list)
        nb_images = self.session.query(Image).count()
        self.assertEqual(len(body), nb_images)

    def test_get(self):
        response = self.app.get('/images/' + str(self.image.document_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertFalse('id' in body)
        self.assertEqual(body.get('document_id'), self.image.document_id)
        self.assertEqual(
            body.get('activities'), self.image.activities)

        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertFalse('id' in locale_en)
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)
        self.assertEqual(locale_en.get('title'), self.locale_en.title)

    def test_post_error(self):
        response = self.app.post_json(
            '/images', {}, expect_errors=True)
        self.assertEqual(response.status_code, 400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'activities is missing')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_missing_title(self):
        body = {
            'activities': 'skitouring',
            'height': 1200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post_json(
            '/images', body, expect_errors=True)
        self.assertEqual(response.status_code, 400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'locales.0.title')

    def test_post_success(self):
        body = {
            'activities': 'hiking',
            'height': 750,
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop'}
            ]
        }
        response = self.app.post_json('/images', body)
        self.assertEqual(response.status_code, 200)

        body = response.json
        document_id = body.get('document_id')
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        image = self.session.query(Image).get(document_id)
        versions = image.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        self.assertEqual(version.culture, 'en')
        self.assertEqual(version.version, 1)
        self.assertEqual(version.nature, 'ft')

        meta_data = version.history_metadata
        self.assertEqual(meta_data.is_minor, False)
        self.assertEqual(meta_data.comment, 'creation')
        self.assertIsNotNone(meta_data.written_at)

        archive_image = version.document_archive
        self.assertEqual(archive_image.document_id, document_id)
        self.assertEqual(archive_image.activities, 'hiking')
        self.assertEqual(archive_image.height, 750)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

    def _add_test_data(self):
        self.image = Image(
            activities='paragliding', height=2000)

        self.locale_en = ImageLocale(
            culture='en', title='Mont Blanc from the air', description='...')

        self.image.locales.append(self.locale_en)

        self.session.add(self.image)
        self.session.flush()
