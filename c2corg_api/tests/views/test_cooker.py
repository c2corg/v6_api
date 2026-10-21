import re

from sqlalchemy import event

from c2corg_api.models.article import Article
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.image import Image
from c2corg_api.tests.views import BaseTestRest


class TestCookerRest(BaseTestRest):
    def setUp(self):  # noqa
        super().setUp()
        self.image_url = self.app.app.registry.settings['image_url']

    def test_get(self):
        markdowns = {'lang': 'fr', 'description': '**strong emphasis** and *emphasis*'}
        response = self.app_post_json('/cooker', markdowns, status=200)

        htmls = response.json

        # lang is not a markdown field, it must be untouched
        self.assertEqual(markdowns['lang'], htmls['lang'])
        self.assertNotEqual(markdowns['description'], htmls['description'])

    def _add_image(self, filename, **kwargs):
        image = Image(
            filename=filename,
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
            **kwargs,
        )
        self.session.add(image)
        self.session.flush()
        return image

    def _cook(self, description):
        response = self.app_post_json(
            '/cooker', {'lang': 'fr', 'description': description}, status=200
        )
        return response.json['description']

    def test_image_known(self):
        image = self._add_image('image.jpg')
        html = self._cook('[img={}/]'.format(image.document_id))

        self.assertIn('c2c:url="{}imageMI.jpg"'.format(self.image_url), html)
        self.assertIn(
            'c2c:url-proxy="/images/proxy/{}?size=MI"'.format(image.document_id), html
        )

    def test_image_unknown(self):
        html = self._cook('[img=999999/]')

        self.assertNotIn('c2c:url=', html)
        self.assertIn('c2c:url-proxy="/images/proxy/999999?size=MI"', html)

    def test_image_id_out_of_range(self):
        # larger than a postgres integer, must not break the query
        html = self._cook('[img=99999999999999999999/]')

        self.assertNotIn('c2c:url=', html)
        self.assertIn('c2c:url-proxy=', html)

    def test_image_redirected(self):
        # the files of a merged image are deleted, use the target ones
        image = self._add_image('image.jpg')
        merged = self._add_image('merged.jpg', redirects_to=image.document_id)
        html = self._cook('[img={}/]'.format(merged.document_id))

        self.assertIn('c2c:url="{}imageMI.jpg"'.format(self.image_url), html)
        self.assertIn(
            'c2c:url-proxy="/images/proxy/{}?size=MI"'.format(merged.document_id), html
        )

    def test_not_an_image(self):
        article = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(article)
        self.session.flush()
        html = self._cook('[img={}/]'.format(article.document_id))

        self.assertNotIn('c2c:url=', html)

    def test_image_sizes_and_svg(self):
        jpg = self._add_image('image.jpg')
        svg = self._add_image('image.svg')
        html = self._cook(
            '[img={0} big/]\n[img={0} orig/]\n[img={1} small/]\n[img={1} orig/]'.format(
                jpg.document_id, svg.document_id
            )
        )

        urls = re.findall(r'c2c:url="([^"]*)"', html)
        self.assertEqual(
            [
                self.image_url + 'imageBI.jpg',
                self.image_url + 'image.jpg',
                self.image_url + 'imageSI.jpg',
                self.image_url + 'image.svg',
            ],
            urls,
        )

    def test_image_url_same_as_proxy(self):
        jpg = self._add_image('image.jpg')
        svg = self._add_image('image.svg')
        merged = self._add_image('merged.jpg', redirects_to=jpg.document_id)
        html = self._cook(
            '[img={0}/]\n[img={0} orig/]\n[img={1} big/]\n'
            '[img={1} orig/]\n[img={2}/]'.format(
                jpg.document_id, svg.document_id, merged.document_id
            )
        )

        imgs = re.findall(r'c2c:url="([^"]*)" c2c:url-proxy="([^"]*)"', html)
        self.assertEqual(5, len(imgs))
        for url, proxy_url in imgs:
            response = self.app.get(proxy_url, status=302)
            self.assertEqual(url, response.headers['Location'])

    def test_images_resolved_with_one_query(self):
        images = [self._add_image('image{}.jpg'.format(i)) for i in range(5)]
        markdowns = {
            'lang': 'fr',
            'description': '\n'.join(
                '[img={}/]'.format(i.document_id) for i in images[:3]
            ),
            'summary': '\n'.join('[img={}/]'.format(i.document_id) for i in images[2:]),
        }

        statements = []

        def count(conn, cursor, statement, *args):
            if 'images' in statement:
                statements.append(statement)

        event.listen(self.connection, 'before_cursor_execute', count)
        try:
            htmls = self.app_post_json('/cooker', markdowns, status=200).json
        finally:
            event.remove(self.connection, 'before_cursor_execute', count)

        self.assertEqual(1, len(statements), statements)
        self.assertEqual(3, htmls['description'].count('c2c:url='))
        self.assertEqual(3, htmls['summary'].count('c2c:url='))

    def test_no_query_without_images(self):
        statements = []

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(self.connection, 'before_cursor_execute', count)
        try:
            self._cook('no image here')
        finally:
            event.remove(self.connection, 'before_cursor_execute', count)

        self.assertEqual([], statements)

    def test_get_cooked_document(self):
        image = self._add_image('image.jpg')
        article = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        article.locales.append(
            DocumentLocale(
                lang='en',
                title='Article',
                description='[img={}/]\n\n[img=999999/]'.format(image.document_id),
            )
        )
        self.session.add(article)
        self.session.flush()

        response = self.app.get(
            '/articles/{}?cook=en'.format(article.document_id), status=200
        )
        html = response.json['cooked']['description']

        self.assertEqual(1, html.count('c2c:url='))
        self.assertIn('c2c:url="{}imageMI.jpg"'.format(self.image_url), html)
        self.assertIn('c2c:url-proxy="/images/proxy/999999?size=MI"', html)
