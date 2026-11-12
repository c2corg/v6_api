import datetime
from dataclasses import dataclass

import pytest

from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.tests import (
    assert_error,
    assert_not_notified_es,
    assert_notified_es,
    auth_headers,
    get_feed_change,
    send_json,
)
from c2corg_api.tests.views import scenarios
from c2corg_api.views.document import create_new_version

PREFIX = '/associations'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    route1: Route
    route2: Route
    image1: Image
    article1: Article
    article2: Article
    report1: Xreport
    outing: Outing


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    user_id = user_ids['contributor']

    waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
    session.add(waypoint1)

    waypoint2 = Waypoint(waypoint_type='summit', elevation=200)
    session.add(waypoint2)
    session.flush()

    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=200,
        redirects_to=waypoint1.document_id,
    )
    session.add(waypoint3)

    route1 = Route(activities=['skitouring'])
    session.add(route1)
    session.add(waypoint2)

    route2 = Route(activities=['skitouring'])
    session.add(route2)

    image1 = Image(
        filename='image.jpg',
        locales=[DocumentLocale(lang='en', title='Mont Blanc from the air')],
    )
    session.add(image1)
    session.flush()
    create_new_version(image1, user_id)

    article1 = Article(
        categories=['site_info'],
        activities=['hiking'],
        article_type='collab',
        locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
    )
    session.add(article1)
    session.flush()
    create_new_version(article1, user_id)

    article2 = Article(
        categories=['site_info'],
        activities=['hiking'],
        article_type='personal',
        locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
    )
    session.add(article2)
    session.flush()
    create_new_version(article2, user_id)

    report1 = Xreport(
        event_activity='alpine_climbing',
        locales=[XreportLocale(lang='en', title="Lac d'Annecy")],
    )
    session.add(report1)
    session.flush()
    create_new_version(report1, user_id)

    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
    )
    session.add(outing)
    session.flush()

    session.add(
        Association(
            parent_document_id=user_id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing.document_id,
            child_document_type=OUTING_TYPE,
        )
    )

    update_feed_document_create(outing, user_id)
    session.flush()

    # create a 2nd feed entry for the outing
    feed_change = get_feed_change(session, outing.document_id)
    user_id = user_ids['moderator']
    feed_change2 = feed_change.copy()
    feed_change2.change_type = 'added_photos'
    feed_change2.user_id = user_id
    feed_change2.user_ids = list(set(feed_change.user_ids).union([user_id]))
    session.add(feed_change2)
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        route1=route1,
        route2=route2,
        image1=image1,
        article1=article1,
        article2=article2,
        report1=report1,
        outing=outing,
    )


def test_add_association_unauthorized(client):
    send_json(client, 'post', PREFIX, {}, status=403)


def test_add_association(client, session, queue_config, docs):
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    association = session.get(
        Association, (docs.waypoint1.document_id, docs.waypoint2.document_id)
    )
    assert association is not None

    association_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == docs.waypoint1.document_id)
        .filter(AssociationLog.child_document_id == docs.waypoint2.document_id)
        .one()
    )
    assert association_log.is_creation is True
    assert association_log.user_id is not None

    assert_notified_es(queue_config)

    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 2)


def test_add_association_wa(client, session, docs):
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    association = session.get(
        Association, (docs.waypoint1.document_id, docs.article1.document_id)
    )
    assert association is not None

    association_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == docs.waypoint1.document_id)
        .filter(AssociationLog.child_document_id == docs.article1.document_id)
        .one()
    )
    assert association_log.is_creation is True
    assert association_log.user_id is not None

    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    scenarios.check_cache_version(session, docs.article1.document_id, 2)


def test_add_association_uo(client, session, user_ids, docs):
    contributor2 = user_ids['contributor2']
    request_body = {
        'parent_document_id': contributor2,
        'child_document_id': docs.outing.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    association = session.get(Association, (contributor2, docs.outing.document_id))
    assert association is not None

    # check that the feed change is updated
    feed_change = get_feed_change(
        session, docs.outing.document_id, change_type='updated'
    )
    assert feed_change is not None
    assert feed_change.change_type == 'updated'
    assert set(feed_change.user_ids) == set(
        [user_ids['contributor'], user_ids['contributor2']]
    )

    # check that the participants of the 2nd feed change are also updated
    feed_change = get_feed_change(
        session, docs.outing.document_id, change_type='added_photos'
    )
    assert feed_change is not None
    assert set(feed_change.user_ids) == set(
        [
            user_ids['contributor'],
            user_ids['contributor2'],
            user_ids['moderator'],
        ]
    )


def test_add_association_uo_no_rights(client, user_ids, docs):
    """Check that associations with outings can only be changed by users
    associated to the outing or moderators.
    """
    contributor2 = user_ids['contributor2']
    request_body = {
        'parent_document_id': contributor2,
        'child_document_id': docs.outing.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.outings',
        f'no rights to modify associations with outing {docs.outing.document_id}',
    )


def test_add_association_wc_article_collab(client, docs):
    """Check that associations with articles can only be changed by
    everyone.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor2')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )


def test_add_association_wc_article_personal_unauthorized(client, session, docs):
    """Check that associations with personal articles can only be changed
    by the creator and moderators.
    """
    docs.article1.article_type = 'personal'
    session.flush()

    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.articles',
        f'no rights to modify associations with article {docs.article1.document_id}',
    )


def test_add_association_wc_article_personal_authorized(client, session, docs):
    """Check that associations with personal articles can only be changed
    by the creator and moderators.
    """
    docs.article1.article_type = 'personal'
    session.flush()

    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )


def test_add_association_cc_article_personal_unauthorized(client, docs):
    """Check that associations with personal articles can only be changed
    by the creator and moderators.
    """
    request_body = {
        'parent_document_id': docs.article2.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.articles',
        f'no rights to modify associations with article {docs.article2.document_id}',
    )


def test_add_association_wi_image_personal_unauthorized(client, session, docs):
    """Check that associations with personal images can only be changed
    by the creator and moderators.
    """
    docs.image1.image_type = 'personal'
    session.flush()

    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.image1.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.images',
        f'no rights to modify associations with image {docs.image1.document_id}',
    )


def test_add_association_wi_image_personal_authorized(client, session, docs):
    """Check that associations with personal images can only be changed
    by the creator and moderators.
    """
    docs.article1.article_type = 'personal'
    session.flush()

    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.image1.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )


def test_add_association_wx_xreport_unauthorized(client, docs):
    """Check that associations with x-reports can only be changed
    by the creator and moderators.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.report1.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.xreports',
        f'no rights to modify associations with xreport {docs.report1.document_id}',
    )


def test_add_association_wx_xreport_authorized(client, docs):
    """Check that associations with x-reports can only be changed
    by the creator and moderators.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.report1.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )


def test_add_association_wc_xreport_article_unauthorized(client, session, docs):
    """Check an association between a xreport and article that both
    do not accept associations from contributor2.
    """
    docs.article1.article_type = 'personal'
    session.flush()

    request_body = {
        'parent_document_id': docs.report1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'associations.xreports',
        f'no rights to modify associations with xreport {docs.report1.document_id}',
    )
    assert_error(
        body['errors'],
        'associations.articles',
        f'no rights to modify associations with article {docs.article1.document_id}',
    )


def test_add_association_duplicate(client, docs):
    """Test that there is only one association between two documents."""
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='contributor')

    # first association, ok
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # 2nd association, fail
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )

    # back-link association also fails
    request_body = {
        'parent_document_id': docs.waypoint2.document_id,
        'child_document_id': docs.waypoint1.document_id,
    }
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )


def test_add_association_invalid(client, docs):
    request_body = {
        'parent_document_id': docs.route1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 1

    assert errors[0].get('name') == 'association'
    assert errors[0].get('description') == 'invalid association type'


def test_add_association_redirected_document(client, docs):
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint3.document_id,
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 1

    assert errors[0].get('name') == 'child_document_id'
    assert (
        errors[0].get('description') == 'child document does not exist or is redirected'
    )


def test_add_association_invalid_ids(client):
    request_body = {
        'parent_document_id': -99,
        'child_document_id': -999,
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=400,
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 2

    assert errors[0].get('name') == 'parent_document_id'
    assert (
        errors[0].get('description')
        == 'parent document does not exist or is redirected'
    )

    assert errors[1].get('name') == 'child_document_id'
    assert (
        errors[1].get('description') == 'child document does not exist or is redirected'
    )


def test_add_association_no_es_update(client, queue_config, docs):
    """Tests that the search index is only updated for specific association
    types.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.image1.document_id,
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    assert_not_notified_es(queue_config)


def test_delete_association_unauthorized(client):
    client.delete_json(PREFIX, {}, status=403)


def test_delete_association_not_existing(client, docs):
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='contributor')

    client.delete_json(PREFIX, request_body, headers=headers, status=400)


def test_delete_association(client, session, queue_config, docs):
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='moderator')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # then delete it again
    client.delete_json(PREFIX, request_body, headers=headers, status=200)

    association = session.get(
        Association, (docs.waypoint1.document_id, docs.waypoint2.document_id)
    )
    assert association is None

    logs = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == docs.waypoint1.document_id)
        .filter(AssociationLog.child_document_id == docs.waypoint2.document_id)
        # written_at is the start of the transaction (now()): the same for
        # both logs when the test runs in one transaction, so also by id
        .order_by(AssociationLog.written_at, AssociationLog.id)
        .all()
    )
    assert logs[0].is_creation is True
    assert logs[1].is_creation is False

    assert_notified_es(queue_config)

    scenarios.check_cache_version(session, docs.waypoint1.document_id, 3)
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 3)


def test_delete_association_non_moderator(client, docs):
    """For non-personal documents, a normal user can create associations
    but not delete them.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='contributor')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # then try to delete it again
    response = client.delete_json(PREFIX, request_body, headers=headers, status=400)
    body = response.json

    assert_error(
        body['errors'],
        'Bad Request',
        'no rights to modify associations between document '
        f'w ({docs.waypoint1.document_id}) and w ({docs.waypoint2.document_id})',
    )


def test_delete_association_fuzzy(client, session, docs):
    """Test that an association {parent: x, child: y} can be
    deleted with {parent: y, child: x}.
    """
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.waypoint2.document_id,
    }
    headers = auth_headers(username='moderator')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # then delete it again, but by switching parent/child id
    request_body = {
        'parent_document_id': docs.waypoint2.document_id,
        'child_document_id': docs.waypoint1.document_id,
    }
    client.delete_json(PREFIX, request_body, headers=headers, status=200)

    association = session.get(
        Association, (docs.waypoint1.document_id, docs.waypoint2.document_id)
    )
    assert association is None


def test_delete_association_main_waypoint(client, session, docs):
    request_body = {
        'parent_document_id': docs.waypoint2.document_id,
        'child_document_id': docs.route1.document_id,
    }
    headers = auth_headers(username='contributor')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # make the wp the main waypoint of the route
    docs.route1.main_waypoint_id = docs.waypoint2.document_id
    session.flush()

    # then try to delete the association
    response = client.delete_json(PREFIX, request_body, headers=headers, status=400)

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 1

    assert errors[0].get('name') == 'Bad Request'
    assert (
        errors[0].get('description') == 'as the main waypoint of the route, '
        'this waypoint can not be disassociated'
    )


def test_delete_association_uo(client, user_ids, docs):
    contributor2 = user_ids['contributor2']
    request_body = {
        'parent_document_id': contributor2,
        'child_document_id': docs.outing.document_id,
    }
    headers = auth_headers(username='contributor')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers,
        status=200,
    )

    # then delete it again
    client.delete_json(PREFIX, request_body, headers=headers, status=200)


def test_delete_association_uo_no_rights(client, user_ids, docs):
    """Try to delete an association to an outing with a user that has
    no permission to change this outing.
    """
    request_body = {
        'parent_document_id': user_ids['contributor'],
        'child_document_id': docs.outing.document_id,
    }

    headers = auth_headers(username='contributor2')
    client.delete_json(PREFIX, request_body, headers=headers, status=400)


def test_delete_association_wc_article_personal(client, session, docs):
    """Test that associations with personal articles require special
    rights.
    """
    docs.article1.article_type = 'personal'
    session.flush()

    # first create an association with the article
    request_body = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.article1.document_id,
    }
    headers1 = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        PREFIX,
        request_body,
        headers=headers1,
        status=200,
    )

    # then try to delete the association again with a different user
    headers2 = auth_headers(username='contributor2')
    response = client.delete_json(PREFIX, request_body, headers=headers2, status=400)
    body = response.json

    assert_error(
        body['errors'],
        'Bad Request',
        'no rights to modify associations between document '
        f'w ({docs.waypoint1.document_id}) and c ({docs.article1.document_id})',
    )

    # but the original user can delete it
    client.delete_json(PREFIX, request_body, headers=headers1, status=200)


def test_delete_association_wp_r_last_waypoint(client, docs):
    request_body1 = {
        'parent_document_id': docs.waypoint2.document_id,
        'child_document_id': docs.route1.document_id,
    }
    headers = auth_headers(username='moderator')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body1,
        headers=headers,
        status=200,
    )

    # try to delete the association
    response = client.delete_json(PREFIX, request_body1, headers=headers, status=400)

    body = response.json
    errors = body.get('errors')
    assert len(errors) == 1
    assert_error(
        errors,
        'Bad Request',
        'as the last waypoint of the route, this waypoint can not be disassociated',
    )

    # add a second waypoint
    request_body2 = {
        'parent_document_id': docs.waypoint1.document_id,
        'child_document_id': docs.route1.document_id,
    }
    send_json(
        client,
        'post',
        PREFIX,
        request_body2,
        headers=headers,
        status=200,
    )

    # now, the first waypoint can be unlinked
    client.delete_json(PREFIX, request_body1, headers=headers)


def test_delete_association_ro_last_route(client, docs):
    request_body1 = {
        'parent_document_id': docs.route1.document_id,
        'child_document_id': docs.outing.document_id,
    }
    headers = auth_headers(username='moderator')

    # add association
    send_json(
        client,
        'post',
        PREFIX,
        request_body1,
        headers=headers,
        status=200,
    )

    # try to delete the association
    response = client.delete_json(PREFIX, request_body1, headers=headers, status=400)

    body = response.json
    errors = body.get('errors')
    assert len(errors) == 1
    assert_error(
        errors,
        'Bad Request',
        'as the last route of the outing, this route can not be disassociated',
    )

    # add a second route
    request_body2 = {
        'parent_document_id': docs.route2.document_id,
        'child_document_id': docs.outing.document_id,
    }
    send_json(
        client,
        'post',
        PREFIX,
        request_body2,
        headers=headers,
        status=200,
    )

    # now, the first route can be unlinked
    client.delete_json(PREFIX, request_body1, headers=headers)
