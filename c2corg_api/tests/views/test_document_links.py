import pytest
from httmock import HTTMock

from c2corg_api.markdown import get_text_references, parse_code
from c2corg_api.models import DBSession
from c2corg_api.models.document_link import DocumentLink
from c2corg_api.scripts.images.rebuild_embeds import rebuild_image_embeds
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import docs  # noqa: F401
from c2corg_api.tests.views.test_document_trash import (  # noqa: F401
    _delete,
    _entry,
    _image,
    _image_service,
    _moderator,
    _restore,
    outing_images,
)
from c2corg_api.views.markdown import cook, update_text_references


def _write(session, document, text):
    """Write this text in the first locale of a document (as saved)."""
    locale = document.locales[0]
    locale.description = text
    session.flush()
    update_text_references([locale])
    session.flush()


def _links(session, document_id):
    """The links stored for a document: [(target id, type, is_url)]."""
    session.expire_all()
    return [
        (link.target_id, link.target_type, link.is_url)
        for link in session.query(DocumentLink)
        .filter(DocumentLink.document_id == document_id)
        .order_by(DocumentLink.target_id, DocumentLink.target_type)
    ]


def _list(client, query='', username='moderator', status=200):
    return client.get(
        '/documents/broken-links' + query,
        headers=auth_headers(username=username),
        status=status,
    )


def _broken(client, query=''):
    return sorted(
        (link['document_id'], link['target_id'], link['target_type'], link['reason'])
        for link in _list(client, query).json['links']
    )


@pytest.mark.parametrize(
    ('text', 'links'),
    [
        ('[[routes/12|a route]]', [('routes', 12, False)]),
        ('[[waypoints/3/fr/slug#anchor|x]]', [('waypoints', 3, False)]),
        # v5 types, typos: kept as written
        ('[[summits/4|x]] [[route/5|x]]', [('summits', 4, False), ('route', 5, False)]),
        (
            '[x](https://www.camptocamp.org/routes/6/fr/slug) '
            '<http://camptocamp.org/Summits/7> '
            '[m](https://m.camptocamp.org/outings/8?x=1)',
            [('routes', 6, True), ('summits', 7, True), ('outings', 8, True)],
        ),
        # not links to a document: a bare URL is not a link, a list, the forum
        (
            'https://www.camptocamp.org/routes/9 '
            '[l](https://www.camptocamp.org/routes#a=1) '
            '[f](https://forum.camptocamp.org/t/10) '
            '[o](https://www.camptocamp.org.example.com/routes/11)',
            [],
        ),
        # not parsed as a link
        ('`[[routes/13|x]]`', []),
    ],
)
def test_text_links(text, links):
    assert get_text_references(text) == ([], links)


def test_links_stored(session, docs):  # noqa: F811
    route_id = docs.route1.document_id
    _write(
        session,
        docs.route1,
        '[img=5/]\n\n[[waypoints/3|a]] [[waypoints/3|b]] '
        '[c](https://www.camptocamp.org/waypoints/3) '
        '[d](https://www.camptocamp.org/summits/4) [[books/99999999999|too large]]',
    )
    # one link per id and type; written both ways counts as [[type/id|label]]
    assert _links(session, route_id) == [(3, 'waypoints', False), (4, 'summits', True)]

    _write(session, docs.route1, 'no link')
    assert _links(session, route_id) == []


def test_links_saved_by_the_api(client, session):
    body = {
        'categories': ['site_info'],
        'activities': ['hiking'],
        'article_type': 'collab',
        'locales': [
            {'lang': 'fr', 'title': 'A', 'description': 'voir [[routes/7|la voie]]'}
        ],
    }
    article_id = client.post_json(
        '/articles', body, headers=auth_headers(username='moderator'), status=200
    ).json['document_id']

    assert _links(session, article_id) == [(7, 'routes', False)]

    _delete(client, article_id)
    assert _links(session, article_id) == []


def test_rebuild(session, docs):  # noqa: F811
    _write(session, docs.route1, '[[waypoints/3|a]]')
    DBSession.query(DocumentLink).delete()
    DBSession.flush()

    _, _, links = rebuild_image_embeds(DBSession, batch_size=1)

    assert links == 1
    assert _links(session, docs.route1.document_id) == [(3, 'waypoints', False)]


def test_broken_links(client, session, docs):  # noqa: F811
    waypoint_id = docs.waypoint1.document_id
    route1_id = docs.route1.document_id
    route2_id = docs.route2.document_id
    _write(
        session,
        docs.route1,
        f'[[waypoints/{waypoint_id}|ok]] [[summits/{waypoint_id}|unknown type]] '
        f'[ok](https://www.camptocamp.org/summits/{waypoint_id}) '
        f'[[routes/{waypoint_id}|wrong type]] [[routes/9999999|missing]] '
        f'[[routes/{route2_id}|merged: redirects]] [[routes/{route1_id}|itself]]',
    )
    docs.route2.redirects_to = docs.route3.document_id
    # a route: the title of its main waypoint before its title
    docs.route1.locales[0].title_prefix = 'Mont Blanc'
    # not a collaborative document: not listed
    _write(session, docs.outing1, '[[routes/9999998|missing]]')
    _write(session, docs.article1, '[[routes/9999998|missing]]')
    # a merged document is not shown
    _write(session, docs.route3, '[[routes/9999998|missing]]')
    docs.route3.redirects_to = route1_id
    session.flush()
    route2_id_merged = route2_id

    body = _list(client).json

    assert body['total'] == 3
    assert _broken(client) == sorted(
        [
            (route1_id, waypoint_id, 'summits', 'unknown_type'),
            (route1_id, waypoint_id, 'routes', 'wrong_type'),
            (route1_id, 9999999, 'routes', 'missing'),
        ]
    )
    wrong = next(link for link in body['links'] if link['reason'] == 'wrong_type')
    assert wrong['document_type'] == 'r'
    assert wrong['title'] == docs.route1.locales[0].title
    assert wrong['title_prefix'] == 'Mont Blanc'
    assert wrong['langs'] == [docs.route1.locales[0].lang]
    assert wrong['is_url'] is False
    assert wrong['target_document_type'] == 'w'
    assert wrong['target_document_title'] == docs.waypoint1.locales[0].title
    assert wrong['target_document_title_prefix'] is None
    assert wrong['deleted'] is None
    assert route2_id_merged not in {link['target_id'] for link in body['links']}


def test_broken_link_deleted_target(client, session, docs):  # noqa: F811
    target = docs.waypoint4
    _write(session, docs.route1, f'[[waypoints/{target.document_id}|deleted]]')
    _write(session, docs.route2, '[[routes/9999999|missing]]')
    _delete(client, target.document_id)

    links = _list(client).json['links']

    # the targets that can be restored first
    assert [(link['target_id'], link['reason']) for link in links] == [
        (target.document_id, 'deleted'),
        (9999999, 'missing'),
    ]
    entry = _entry(session, target.document_id)
    assert links[0]['deleted']['entry_id'] == entry.id
    assert links[0]['deleted']['document_type'] == 'w'

    _restore(client, entry.id)
    assert [link['target_id'] for link in _list(client).json['links']] == [9999999]


def test_broken_links_page(client, session, docs):  # noqa: F811
    _write(session, docs.route1, '[[routes/9999997|a]] [[routes/9999998|b]]')

    body = _list(client, '?offset=1&limit=1').json

    assert body['total'] == 2
    assert [link['target_id'] for link in body['links']] == [9999998]


def test_broken_links_reserved_to_the_moderators(client):
    _list(client, username='contributor', status=403)
    client.get('/documents/broken-links', status=403)


def test_orphan_images_linked_from(client, session, user_ids, docs):  # noqa: F811
    orphan = _image(session, user_ids, 'contributor', 'personal', [], 'orphan')
    image_id = orphan.document_id
    _write(
        session,
        docs.route1,
        f'[[images/{image_id}|photo]] [[routes/{image_id}|wrong type: not a link]]',
    )

    images = client.get(
        '/images/orphans', headers=auth_headers(username='moderator'), status=200
    ).json['images']

    image = next(i for i in images if i['document_id'] == image_id)
    assert image['linked_from'] == [
        {
            'document_id': docs.route1.document_id,
            'document_type': 'r',
            'title': docs.route1.locales[0].title,
            'langs': [docs.route1.locales[0].lang],
        }
    ]
    assert image['embedded_in'] == []


def test_personal_image_linked_elsewhere_kept(client, session, outing_images, docs):  # noqa: F811
    photo_id = outing_images['photo'].document_id
    url = f'/documents/delete/{docs.outing2.document_id}/images'
    assert client.get(url, headers=_moderator()).json['deleted'] == 1
    # linked from the text of a route: kept, orphan
    _write(session, docs.route1, f'[[images/{photo_id}|the photo]]')
    assert client.get(url, headers=_moderator()).json['deleted'] == 0

    with HTTMock(_image_service):
        _delete(client, docs.outing2.document_id)

    assert session.get(type(outing_images['photo']), photo_id) is not None


def test_parse_code_link_type_resolver():
    def resolver(document_id):
        return {3: 'waypoints'}.get(document_id)

    html = parse_code('[[summits/3|a]] [[routes/4|b]]', link_type_resolver=resolver)

    # the type of the document of the id; an unknown id keeps its type
    assert 'c2c:document-id="3" c2c:document-type="waypoints"' in html
    assert 'c2c:document-id="4" c2c:document-type="routes"' in html
    # the links stored are the ones written
    assert get_text_references('[[summits/3|a]]') == ([], [('summits', 3, False)])


def test_cook_leads_wrong_types_to_the_document(docs):  # noqa: F811
    waypoint_id = docs.waypoint1.document_id
    route_id = docs.route1.document_id

    cooked = cook(
        {
            'lang': 'fr',
            'description': f'[[routes/{waypoint_id}|a]] [[parkings/{waypoint_id}|b]]',
            'summary': f'[[routes/{route_id}|c]] [[routes/9999999|d]]',
        }
    )

    assert cooked['description'].count('c2c:document-type="waypoints"') == 2
    assert (
        f'c2c:document-id="{route_id}" c2c:document-type="routes"'
        in (cooked['summary'])
    )
    assert 'c2c:document-id="9999999" c2c:document-type="routes"' in (cooked['summary'])
