from c2corg_api.models.image import Image, ImageLocale

from c2corg_api.tests.views import BaseTestRest


class TestImageRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model("/images", Image)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        self.get(self.image)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertMissing(errors[0], 'activities')

    def test_post_missing_title(self):
        body = {
            'activities': 'skitouring',
            'height': 1200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post_json(
            '/images', body, expect_errors=True, status=400)

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
        body, doc = self.post_success(body)
        version = doc.versions[0]

        archive_image = version.document_archive
        self.assertEqual(archive_image.activities, 'hiking')
        self.assertEqual(archive_image.height, 750)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

    def _add_test_data(self):
        self.image = Image(
            activities='paragliding', height=2000)

        self.locale_en = ImageLocale(
            culture='en', title='Mont Blanc from the air', description='...')

        self.locale_fr = ImageLocale(
            culture='fr', title='Mont Blanc du ciel', description='...')

        self.image.locales.append(self.locale_en)
        self.image.locales.append(self.locale_fr)

        self.session.add(self.image)
        self.session.flush()
