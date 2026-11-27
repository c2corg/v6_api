import pytest

from c2corg_api.markdown import get_text_references, get_url_host
from c2corg_api.models import DBSession
from c2corg_api.models.external_link import ExternalLink
from c2corg_api.scripts.images.rebuild_embeds import rebuild_image_embeds
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import docs  # noqa: F401
from c2corg_api.tests.views.test_document_trash import _delete
from c2corg_api.views.markdown import update_text_references


def _write(session, document, text):
    """Write this text in the first locale of a document (as saved)."""
    locale = document.locales[0]
    locale.description = text
    session.flush()
    update_text_references([locale])
    session.flush()


def _external(session, document_id):
    """The external links stored for a document: [(url, host)]."""
    session.expire_all()
    return sorted(
        (link.url, link.host)
        for link in session.query(ExternalLink).filter(
            ExternalLink.document_id == document_id
        )
    )


@pytest.mark.parametrize(
    ('text', 'urls'),
    [
        (
            '[a blog](http://blog.example.com/topo?a=1&b=2#x)',
            ['http://blog.example.com/topo?a=1&b=2#x'],
        ),
        ('<https://example.org/page>', ['https://example.org/page']),
        # raw HTML links too, each URL once, in order
        (
            '<a href="https://b.example/">b</a> [a](https://a.example/) [b](https://b.example/)',
            ['https://b.example/', 'https://a.example/'],
        ),
        # the other URLs of the site are external links, its documents are not
        (
            '[f](https://forum.camptocamp.org/t/10) '
            '[d](https://www.camptocamp.org/routes/6/fr/slug) '
            '[l](https://www.camptocamp.org/routes#a=1)',
            [
                'https://forum.camptocamp.org/t/10',
                'https://www.camptocamp.org/routes#a=1',
            ],
        ),
        # not links: a bare URL, mail, code, a scheme the cleaner drops
        (
            'https://example.com/bare [m](mailto:a@example.com) '
            '`[c](https://example.com/code)` '
            '<a href="javascript:alert(1)">j</a> [[routes/3|r]]',
            [],
        ),
        # too long to be tracked
        ('[x](https://example.com/' + 'a' * 2000 + ')', []),
    ],
)
def test_text_urls(text, urls):
    assert get_text_references(text)[2] == urls


@pytest.mark.parametrize(
    ('url', 'host'),
    [
        ('https://Blog.Example.COM:8080/x', 'blog.example.com'),
        ('https://user@evil.example/', 'evil.example'),
        ('http://camptocamp.org./', 'camptocamp.org'),
        ('https://[::1/', None),
        ('https:///path', None),
    ],
)
def test_url_host(url, host):
    assert get_url_host(url) == host


def test_external_links_stored(session, docs):  # noqa: F811
    route_id = docs.route1.document_id
    _write(
        session,
        docs.route1,
        '[a](https://Example.com/A) [b](https://example.com/A) '
        '[c](https://www.camptocamp.org/routes/3)',
    )
    # as written: the path is case-sensitive, the host lowercase
    assert _external(session, route_id) == [
        ('https://Example.com/A', 'example.com'),
        ('https://example.com/A', 'example.com'),
    ]

    _write(session, docs.route1, 'no link')
    assert _external(session, route_id) == []


def test_external_links_saved_by_the_api(client, session):
    body = {
        'categories': ['site_info'],
        'activities': ['hiking'],
        'article_type': 'collab',
        'locales': [
            {
                'lang': 'fr',
                'title': 'A',
                'description': 'voir [le refuge](https://refuge.example/)',
                'summary': 'et <https://meteo.example/>',
            }
        ],
    }
    article_id = client.post_json(
        '/articles', body, headers=auth_headers(username='moderator'), status=200
    ).json['document_id']

    assert _external(session, article_id) == [
        ('https://meteo.example/', 'meteo.example'),
        ('https://refuge.example/', 'refuge.example'),
    ]

    _delete(client, article_id)
    assert _external(session, article_id) == []


def test_rebuild(session, docs):  # noqa: F811
    _write(session, docs.route1, '[a](https://example.com/)')
    DBSession.query(ExternalLink).delete()
    DBSession.flush()

    _, _, _, external = rebuild_image_embeds(DBSession, batch_size=1)

    assert external == 1
    assert _external(session, docs.route1.document_id) == [
        ('https://example.com/', 'example.com')
    ]
