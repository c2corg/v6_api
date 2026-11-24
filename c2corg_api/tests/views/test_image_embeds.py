import pytest

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image_embed import ImageEmbed
from c2corg_api.models.route import RouteLocale
from c2corg_api.scripts.images.rebuild_embeds import rebuild_image_embeds
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_trash import _delete, _entry, _restore
from c2corg_api.views.markdown import get_locale_image_ids


def _embeds(session, document_id):
    """The embeds of a document: {lang: [image ids]}."""
    session.expire_all()
    embeds = {}
    for embed in (
        session.query(ImageEmbed)
        .filter(ImageEmbed.document_id == document_id)
        .order_by(ImageEmbed.lang, ImageEmbed.image_id)
    ):
        embeds.setdefault(embed.lang, []).append(embed.image_id)
    return embeds


def _post_article(client, locales):
    body = {
        'categories': ['site_info'],
        'activities': ['hiking'],
        'article_type': 'collab',
        'locales': locales,
    }
    return client.post_json(
        '/articles', body, headers=auth_headers(username='moderator'), status=200
    ).json['document_id']


def _put_article(client, document_id, locales):
    article = client.get(f'/articles/{document_id}', status=200).json
    article['locales'] = [
        {**locale, **locales[locale['lang']]}
        for locale in article['locales']
        if locale['lang'] in locales
    ]
    client.put_json(
        f'/articles/{document_id}',
        {'message': 'Update', 'document': article},
        headers=auth_headers(username='moderator'),
        status=200,
    )


@pytest.fixture
def article_id(client):
    return _post_article(
        client,
        [
            {
                'lang': 'fr',
                'title': '[img=9/]',
                'summary': '[img=3/]',
                'description': 'Texte\n[img=1 right]Légende[/img]\n\n[img=2/]',
            },
            # not shown: no embed (mid-line, too large an id)
            {
                'lang': 'en',
                'title': 'Title',
                'description': 'see [img=4/]\n[img=99999999999/]',
            },
        ],
    )


def test_locale_image_ids_of_every_text_cooked():
    locale = RouteLocale(
        lang='fr',
        title='[img=1/]',
        slope='[img=2/]',
        description='[img=3/]',
        gear='[img=4/]',
        slackline_anchor1='[img=5/]',
    )
    assert get_locale_image_ids(locale) == {3, 4, 5}


def test_created(session, article_id):
    assert _embeds(session, article_id) == {'fr': [1, 2, 3]}


def test_updated(client, session, article_id):
    _put_article(
        client,
        article_id,
        {'fr': {'description': '[img=5/]'}, 'en': {'description': '[img=6/]'}},
    )
    assert _embeds(session, article_id) == {'en': [6], 'fr': [3, 5]}


def test_locale_added(client, session, article_id):
    article = client.get(f'/articles/{article_id}', status=200).json
    article['locales'] = [{'lang': 'de', 'title': 'Titel', 'summary': '[img=7/]'}]
    client.put_json(
        f'/articles/{article_id}',
        {'message': 'Deutsch', 'document': article},
        headers=auth_headers(username='moderator'),
        status=200,
    )
    assert _embeds(session, article_id) == {'de': [7], 'fr': [1, 2, 3]}


def test_reverted(client, session, article_id):
    (first_version,) = (
        session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == article_id)
        .filter(DocumentVersion.lang == 'fr')
        .order_by(DocumentVersion.id)
        .first()
    )
    _put_article(client, article_id, {'fr': {'description': None}})
    assert _embeds(session, article_id) == {'fr': [3]}

    client.post_json(
        '/documents/revert',
        {'document_id': article_id, 'lang': 'fr', 'version_id': first_version},
        headers=auth_headers(username='moderator'),
        status=200,
    )
    assert _embeds(session, article_id) == {'fr': [1, 2, 3]}


def test_locale_deleted_and_restored(client, session, article_id):
    _put_article(client, article_id, {'en': {'description': '[img=6/]'}})

    _delete(client, article_id, 'fr')
    assert _embeds(session, article_id) == {'en': [6]}

    _restore(client, _entry(session, article_id, 'fr').id)
    assert _embeds(session, article_id) == {'en': [6], 'fr': [1, 2, 3]}


def test_document_deleted_and_restored(client, session, article_id):
    _delete(client, article_id)
    assert _embeds(session, article_id) == {}

    _restore(client, _entry(session, article_id).id)
    assert _embeds(session, article_id) == {'fr': [1, 2, 3]}


def test_rebuild(session, article_id):
    # lost embeds (as before the first run), and a stale one
    DBSession.query(ImageEmbed).delete()
    DBSession.add(
        ImageEmbed(
            document_locale_id=_locale_id(article_id, 'en'),
            image_id=8,
            document_id=article_id,
            lang='en',
        )
    )
    DBSession.flush()

    locales, embeds = rebuild_image_embeds(DBSession, batch_size=1)

    assert (locales, embeds) == (2, 3)
    assert _embeds(session, article_id) == {'fr': [1, 2, 3]}


def _locale_id(document_id, lang):
    return (
        DBSession.query(DocumentLocale.id)
        .filter_by(document_id=document_id, lang=lang)
        .scalar()
    )
