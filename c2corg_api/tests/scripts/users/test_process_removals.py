import datetime
from unittest.mock import Mock

import pytest

from c2corg_api.models.account_removal import AccountRemovalRequest
from c2corg_api.models.deleted_document import DeletedDocument
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user import User
from c2corg_api.scripts.users.process_removals import (
    ForumDisabledError,
    find_purged_documents,
    find_ready_requests,
    process_removal,
)
from c2corg_api.security.discourse_client import (
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.views.document import create_new_version

NOW = datetime.datetime.now(datetime.UTC)


@pytest.fixture(autouse=True)
def discourse(settings):
    """Mock the Discourse client; restore the real one after the test."""
    original = get_discourse_client(settings)
    mock = Mock()
    set_discourse_client(mock)
    yield mock
    set_discourse_client(original)


def make_removal(session, user_ids, reason='merge', **kwargs):
    values = {
        'user_id': user_ids['contributor'],
        'forum_id': 1234,
        'user_name': 'Contributor',
        'user_forum_username': 'contributor',
        'reason': reason,
        'executable_after': NOW.date() - datetime.timedelta(days=1),
        'target_user_id': user_ids['contributor2'],
        'target_forum_id': 49513,
        'requested_by': user_ids['moderator'],
        'topoguide_validated_by': user_ids['moderator'],
        'topoguide_validated_at': NOW - datetime.timedelta(days=3),
        'forum_validated_by': user_ids['contributor3'],
        'forum_validated_at': NOW - datetime.timedelta(days=3),
    }
    values.update(kwargs)
    removal = AccountRemovalRequest(**values)
    session.add(removal)
    session.flush()
    return removal


def make_outing(session, user_id):
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        elevation_max=1500,
        locales=[OutingLocale(lang='en', title='spam')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'
        ),
    )
    session.add(outing)
    session.flush()
    create_new_version(outing, user_id)
    return outing


class TestFindReadyRequests:
    def test_ready(self, session, user_ids):
        removal = make_removal(session, user_ids)
        # compare the ids: the function reads with DBSession, not this session
        assert [r.id for r in find_ready_requests(NOW)] == [removal.id]

    def test_not_validated_by_both_sides(self, session, user_ids):
        make_removal(
            session, user_ids, forum_validated_by=None, forum_validated_at=None
        )
        assert find_ready_requests(NOW) == []

    def test_date_not_reached(self, session, user_ids):
        make_removal(
            session,
            user_ids,
            executable_after=NOW.date() + datetime.timedelta(days=1),
        )
        assert find_ready_requests(NOW) == []

    def test_grace_delay(self, session, user_ids):
        make_removal(
            session, user_ids, forum_validated_at=NOW - datetime.timedelta(hours=2)
        )
        assert find_ready_requests(NOW) == []
        assert len(find_ready_requests(NOW, grace_hours=1)) == 1

    def test_done(self, session, user_ids):
        make_removal(session, user_ids, done_at=NOW)
        assert find_ready_requests(NOW) == []

    def test_cancelled(self, session, user_ids):
        make_removal(session, user_ids, cancelled_at=NOW, cancelled_by=1)
        assert find_ready_requests(NOW) == []


class TestProcessRemoval:
    def test_merge(self, session, user_ids, queue_config, settings, discourse):
        removal = make_removal(session, user_ids)
        source_id = user_ids['contributor']

        process_removal(removal.id, settings, queue_config)

        discourse.merge_user.assert_called_once_with(source_id, 49513)
        discourse.delete_user.assert_not_called()
        session.expire_all()
        assert removal.done_at is not None
        assert session.get(User, source_id) is None
        assert session.get(User, user_ids['contributor2']) is not None

    def test_forum_error(self, session, user_ids, queue_config, settings, discourse):
        discourse.merge_user.side_effect = Exception('forum down')
        removal = make_removal(session, user_ids)

        with pytest.raises(Exception, match='forum down'):
            process_removal(removal.id, settings, queue_config)

        # nothing is removed, the request will be processed again
        session.expire_all()
        assert removal.done_at is None
        assert session.get(User, user_ids['contributor']) is not None

    def test_forum_disabled(self, session, user_ids, queue_config, settings, discourse):
        # the forum account would stay: nothing is done
        discourse.enabled = False
        removal = make_removal(session, user_ids)

        with pytest.raises(ForumDisabledError):
            process_removal(removal.id, settings, queue_config)

        discourse.merge_user.assert_not_called()
        session.expire_all()
        assert removal.done_at is None
        assert session.get(User, user_ids['contributor']) is not None

    @pytest.mark.parametrize(
        'change',
        [
            # a validation cancelled after the list of the ready requests
            {'forum_validated_by': None, 'forum_validated_at': None},
            {'cancelled_by': 1, 'cancelled_at': NOW},
            {'done_at': NOW},
        ],
    )
    def test_not_ready_anymore(
        self, session, user_ids, queue_config, settings, discourse, change
    ):
        removal = make_removal(session, user_ids)
        for name, value in change.items():
            setattr(removal, name, value)
        session.flush()

        assert process_removal(removal.id, settings, queue_config) is False

        discourse.merge_user.assert_not_called()
        assert session.get(User, user_ids['contributor']) is not None

    def test_spam(self, session, user_ids, queue_config, settings, discourse):
        source_id = user_ids['contributor']
        spam = make_outing(session, source_id)
        spam.locales[0].document_topic = DocumentTopic(topic_id=77)
        spam_id = spam.document_id
        shared = make_outing(session, source_id)
        shared_id = shared.document_id
        # someone else contributed to the second one: a new version, as an
        # update does (the archive of the version 1 already exists)
        shared.version += 1
        shared.geometry.version += 1
        for locale in shared.locales:
            locale.version += 1
        session.flush()
        create_new_version(shared, user_ids['contributor2'])

        assert find_purged_documents(source_id) == [(spam_id, spam.type)]

        removal = make_removal(session, user_ids, reason='spam')
        process_removal(removal.id, settings, queue_config)

        discourse.delete_user.assert_called_once_with(source_id, delete_posts=True)
        discourse.merge_user.assert_not_called()
        session.expire_all()
        assert removal.done_at is not None
        assert session.get(Document, spam_id) is None
        assert session.get(Document, shared_id) is not None
        assert session.get(User, source_id) is None
        # deleted for good, its comment topic closed and unlisted
        assert session.query(DeletedDocument).count() == 0
        status = discourse.client.update_topic_status
        assert status.call_args_list == [
            ((77, 'closed', True),),
            ((77, 'visible', False),),
        ]
