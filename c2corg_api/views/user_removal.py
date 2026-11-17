"""The requests to anonymize, merge or delete a user account.

A moderator (of the topoguide or of the forum) makes a request. It must then be
validated by a moderator of the topoguide and by a moderator of the forum: three
different persons. The account is removed afterwards by the script
`c2corg_api/scripts/users/process_removals.py`, once the date of the request is
past.
"""

import datetime
import logging

from pydiscourse.exceptions import DiscourseClientError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.functions import func

from c2corg_api import DBSession
from c2corg_api.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPNotFound,
    HTTPServiceUnavailable,
)
from c2corg_api.models.account_removal import (
    ACTION_CANCEL,
    ACTION_CREATE,
    ACTION_UNVALIDATE,
    ACTION_UPDATE,
    ACTION_VALIDATE,
    REASON_MERGE,
    REASONS,
    SIDE_FORUM,
    SIDE_TOPOGUIDE,
    SIDES,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_VALIDATED,
    AccountRemovalRequest,
)
from c2corg_api.models.user import User
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Date, Int, OneOf, Str
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.resource import write
from c2corg_api.views.validation import validate_id

log = logging.getLogger(__name__)

# The accounts the anonymized and spam accounts are merged into ("Compte
# fermé"), in the topoguide and in the forum; settings for the tests.
CLOSED_ACCOUNT_ID = 811780
CLOSED_ACCOUNT_FORUM_ID = 49513

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def _http_url(value):
    # shown as a link to the other moderators: never a javascript: URL
    if not value.lower().startswith(('https://', 'http://')):
        return 'Must be an http(s) URL'
    return None


ForumUrl = Str(500, checks=[_http_url])


class CreateRemovalSchema(Schema):
    user_id: Int
    reason: OneOf(REASONS)
    executable_after: Date
    # an anonymization or a spam goes to the closed account: optional then
    target_user_id: Int = None
    # found by the API, checked if given
    target_forum_id: Int = None
    forum_url: ForumUrl = None


class ValidateRemovalSchema(Schema):
    side: OneOf(SIDES)


class UnvalidateRemovalSchema(Schema):
    side: OneOf(SIDES)
    # the discussion in which the validation is questioned
    forum_url: ForumUrl


class ForumUrlSchema(Schema):
    # the discussion of the request (update), or why it is cancelled (cancel)
    forum_url: ForumUrl


def _closed_accounts(settings):
    return (
        int(settings.get('users.closed_account_id', CLOSED_ACCOUNT_ID)),
        int(settings.get('users.closed_account_forum_id', CLOSED_ACCOUNT_FORUM_ID)),
    )


def _forum_unavailable():
    log.error('Asking the forum failed', exc_info=True)
    return HTTPServiceUnavailable('The forum does not answer')


def _is_forum_moderator(request, user_id, strict=False):
    """Tell whether a user is a moderator of the forum.

    If the forum does not answer, the user is considered as not being one,
    unless `strict` (the check protects an action): the action is then refused.
    """
    try:
        client = get_discourse_client(request.registry.settings)
        return bool(client.is_moderator(user_id))
    except Exception as e:
        if strict:
            raise _forum_unavailable() from e
        log.error('Checking the Discourse moderator failed: %d', user_id, exc_info=True)
        return False


def _check_side(request, side):
    """Check that the authenticated user is a moderator of the side."""
    if side == SIDE_TOPOGUIDE:
        allowed = request.has_permission('moderator')
    else:
        allowed = _is_forum_moderator(
            request, request.authenticated_userid, strict=True
        )
    if not allowed:
        raise HTTPForbidden(f'You are not a moderator of the {side}')


def _check_moderator(request):
    """Return the roles {topoguide, forum} of the user, who has at least one."""
    if request.authenticated_userid is None:
        raise HTTPForbidden('Only the moderators can manage the removal requests')
    topoguide = bool(request.has_permission('moderator'))
    # a moderator of the topoguide is not blocked by a forum which is down
    forum = _is_forum_moderator(
        request, request.authenticated_userid, strict=not topoguide
    )
    if not topoguide and not forum:
        raise HTTPForbidden('Only the moderators can manage the removal requests')
    return {SIDE_TOPOGUIDE: topoguide, SIDE_FORUM: forum}


def _get_request(request_id):
    # locked until the end of the transaction: two moderators acting at once
    # on the same request are served one after the other
    removal = (
        DBSession.query(AccountRemovalRequest)
        .filter(AccountRemovalRequest.id == request_id)
        .with_for_update()
        .one_or_none()
    )
    if not removal:
        raise HTTPNotFound(f'Unknown removal request {request_id}')
    return removal


def _check_open(removal):
    if removal.status == STATUS_DONE:
        raise HTTPBadRequest('The account has already been removed')
    if removal.status == STATUS_CANCELLED:
        raise HTTPBadRequest('The request has been cancelled')


def _log(removal, action, user_id, **details):
    # a new list: JSONB changes made in place are not seen; None before insert
    removal.history = [
        *(removal.history or []),
        {
            'action': action,
            'by': user_id,
            'at': datetime.datetime.now(datetime.UTC).isoformat(),
            **details,
        },
    ]


def _other(side):
    return SIDE_FORUM if side == SIDE_TOPOGUIDE else SIDE_TOPOGUIDE


def _validation_refused(removal, side, user_id):
    """Return why the user cannot validate this side (a moderator of it), or None."""
    if removal.requested_by == user_id:
        return 'The author of a request cannot validate it'
    if getattr(removal, f'{_other(side)}_validated_by') == user_id:
        return 'Only one side of a request can be validated by a person'
    return None


def _actions(removal, roles, user_id):
    """Return what the user can do with the request: the buttons of the UI."""
    open_ = removal.status in (STATUS_IN_PROGRESS, STATUS_VALIDATED)
    return {
        'validate': [
            side
            for side in SIDES
            if open_
            and roles[side]
            and getattr(removal, f'{side}_validated_by') is None
            and _validation_refused(removal, side, user_id) is None
        ],
        'unvalidate': [
            side
            for side in SIDES
            if open_
            and roles[side]
            and getattr(removal, f'{side}_validated_by') is not None
        ],
        'update': removal.status == STATUS_IN_PROGRESS,
        'cancel': open_,
    }


def _serialize_all(removals, roles, user_id):
    ids = set()
    for removal in removals:
        ids.update(
            (
                removal.requested_by,
                removal.topoguide_validated_by,
                removal.forum_validated_by,
                removal.cancelled_by,
                *(event['by'] for event in removal.history),
            )
        )
    ids.discard(None)
    names = {}
    if ids:
        names = dict(DBSession.query(User.id, User.name).filter(User.id.in_(ids)).all())

    def person(user_id):
        if user_id is None:
            return None
        # the name is missing if the moderator account has been removed since
        return {'id': user_id, 'name': names.get(user_id)}

    def iso(value):
        return value.isoformat() if value is not None else None

    return [
        {
            'id': removal.id,
            'user_id': removal.user_id,
            'forum_id': removal.forum_id,
            'user_name': removal.user_name,
            'user_forum_username': removal.user_forum_username,
            'reason': removal.reason,
            'executable_after': iso(removal.executable_after),
            'target_user_id': removal.target_user_id,
            'target_forum_id': removal.target_forum_id,
            'forum_url': removal.forum_url,
            'created_at': iso(removal.created_at),
            'requested_by': person(removal.requested_by),
            'topoguide_validated_by': person(removal.topoguide_validated_by),
            'topoguide_validated_at': iso(removal.topoguide_validated_at),
            'forum_validated_by': person(removal.forum_validated_by),
            'forum_validated_at': iso(removal.forum_validated_at),
            'cancelled_by': person(removal.cancelled_by),
            'cancelled_at': iso(removal.cancelled_at),
            'done_at': iso(removal.done_at),
            'status': removal.status,
            # when the script will process it, once validated
            'ready_at': iso(removal.ready_at()),
            'history': [
                {**event, 'by': person(event['by'])} for event in removal.history
            ],
            'can': _actions(removal, roles, user_id),
        }
        for removal in removals
    ]


def _answer(request, removal, roles=None):
    if roles is None:
        roles = _check_moderator(request)
    DBSession.flush()
    DBSession.refresh(removal)
    return _serialize_all([removal], roles, request.authenticated_userid)[0]


def _open_requests():
    return DBSession.query(AccountRemovalRequest).filter(
        AccountRemovalRequest.done_at.is_(None),
        AccountRemovalRequest.cancelled_at.is_(None),
    )


def read_removal_requests(request):
    """Get the removal requests, the open ones first, then the newest.

    Request:
        `GET` `/users/removals?status=in_progress&offset=0&limit=30`

    Example response:

        {
            'total': 1,
            'removals': [{'id': 1, 'user_id': 123, 'status': 'in_progress',
                          'can': {'validate': ['forum'], ...}, ...}],
            'roles': {'topoguide': true, 'forum': false}
        }
    """
    roles = _check_moderator(request)
    validated = request.validated
    query = DBSession.query(AccountRemovalRequest)
    status = validated.get('status')
    if status == STATUS_DONE:
        query = query.filter(AccountRemovalRequest.done_at.is_not(None))
    elif status == STATUS_CANCELLED:
        query = query.filter(AccountRemovalRequest.cancelled_at.is_not(None))
    elif status in (STATUS_IN_PROGRESS, STATUS_VALIDATED):
        both = AccountRemovalRequest.topoguide_validated_by.is_not(
            None
        ) & AccountRemovalRequest.forum_validated_by.is_not(None)
        query = _open_requests().filter(both if status == STATUS_VALIDATED else ~both)
    total = query.count()
    removals = (
        query.order_by(
            (
                AccountRemovalRequest.done_at.is_not(None)
                | AccountRemovalRequest.cancelled_at.is_not(None)
            ),
            AccountRemovalRequest.created_at.desc(),
            AccountRemovalRequest.id.desc(),
        )
        .offset(validated.get('offset') or 0)
        .limit(min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX))
        .all()
    )
    return {
        'total': total,
        'removals': _serialize_all(removals, roles, request.authenticated_userid),
        'roles': roles,
    }


def read_removal_requests_count(request):
    """Get the number of removal requests not done yet, and the roles of the user.

    Request:
        `GET` `/users/removals/count`

    Example response:

        {'open': 2, 'roles': {'topoguide': true, 'forum': false}}

    Like the list, it is for the moderators of the topoguide and of the forum.
    """
    roles = _check_moderator(request)
    count = _open_requests().with_entities(func.count(AccountRemovalRequest.id))
    return {'open': count.scalar(), 'roles': roles}


def _targets(request, validated, user_id):
    """Return the accounts (topoguide, forum) the account goes to."""
    settings = request.registry.settings
    client = get_discourse_client(settings)
    target_user_id = validated.get('target_user_id')
    if validated['reason'] == REASON_MERGE:
        if target_user_id is None:
            raise HTTPBadRequest('The account to merge into is missing')
        # the forum account of the target: never one given by the client,
        # the forum merge cannot be undone
        try:
            target_forum_id = client.get_userid(target_user_id)
        except DiscourseClientError as e:
            if e.response is None or e.response.status_code != 404:
                raise _forum_unavailable() from e
            raise HTTPBadRequest(
                f'The user {target_user_id} has no forum account'
            ) from e
        except Exception as e:
            raise _forum_unavailable() from e
    else:
        closed_id, closed_forum_id = _closed_accounts(settings)
        if target_user_id not in (None, closed_id):
            raise HTTPBadRequest(
                'An anonymized or spam account goes to the closed account'
            )
        target_user_id, target_forum_id = closed_id, closed_forum_id

    given = validated.get('target_forum_id')
    if given is not None and given != target_forum_id:
        raise HTTPBadRequest(
            f'The forum account to merge into is {target_forum_id}, not {given}'
        )
    if target_user_id == user_id:
        raise HTTPBadRequest('The account cannot be merged into itself')
    if not DBSession.get(User, target_user_id):
        raise HTTPBadRequest(f'Unknown user {target_user_id}')
    return target_user_id, target_forum_id


@write(
    validators=[body_validator(CreateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def create_removal_request(request):
    """Request the removal of a user account.

    Request:
        `POST` `/users/removals`

    Request body:
        {
            'user_id': @user_id@,
            'reason': 'anonymization' | 'merge' | 'spam',
            'executable_after': '2026-12-01',
            'target_user_id': @user_id@,      # merge only
            'forum_url': 'https://forum...'   # optional
        }

    An anonymized or spam account goes to the closed account; a merged one to
    the given account, and to its forum account.
    """
    roles = _check_moderator(request)
    validated = request.validated
    user_id = validated['user_id']

    user = DBSession.get(User, user_id)
    if not user:
        raise HTTPBadRequest(f'Unknown user {user_id}')
    # neither of the topoguide nor of the forum: the forum check is strict
    if user.moderator or _is_forum_moderator(request, user_id, strict=True):
        raise HTTPBadRequest('A moderator account cannot be removed')
    if validated['executable_after'] < datetime.datetime.now(datetime.UTC).date():
        raise HTTPBadRequest('The date of the removal cannot be in the past')
    target_user_id, target_forum_id = _targets(request, validated, user_id)

    if _open_requests().filter(AccountRemovalRequest.user_id == user_id).count():
        raise HTTPConflict(f'The user {user_id} already has a removal request')

    forum_id = None
    try:
        forum_id = get_discourse_client(request.registry.settings).get_userid(user_id)
    except Exception:
        # the forum account is searched again when the account is removed
        log.warning('Finding the forum account failed: %d', user_id, exc_info=True)
    if forum_id is not None and forum_id == target_forum_id:
        raise HTTPBadRequest('The forum account cannot be merged into itself')

    removal = AccountRemovalRequest(
        user_id=user_id,
        forum_id=forum_id,
        user_name=user.name,
        user_forum_username=user.forum_username,
        reason=validated['reason'],
        executable_after=validated['executable_after'],
        target_user_id=target_user_id,
        target_forum_id=target_forum_id,
        forum_url=validated.get('forum_url'),
        requested_by=request.authenticated_userid,
    )
    _log(
        removal,
        ACTION_CREATE,
        request.authenticated_userid,
        forum_url=removal.forum_url,
    )
    try:
        # a savepoint: the same request made twice at once
        with DBSession.begin_nested():
            DBSession.add(removal)
    except IntegrityError as e:
        raise HTTPConflict(f'The user {user_id} already has a removal request') from e
    return _answer(request, removal, roles)


@write(
    validators=[validate_id, body_validator(ValidateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def validate_removal_request(request):
    """Validate a removal request, as a moderator of the topoguide or the forum.

    The author of the request cannot validate it, and nobody can validate both
    sides of it.

    Request:
        `POST` `/users/removals/{id}/validate`

    Request body:
        {'side': 'topoguide' | 'forum'}
    """
    side = request.validated['side']
    _check_side(request, side)
    removal = _get_request(request.validated['id'])
    _check_open(removal)

    user_id = request.authenticated_userid
    if getattr(removal, f'{side}_validated_by') is not None:
        raise HTTPConflict(f'The request is already validated by the {side}')
    refused = _validation_refused(removal, side, user_id)
    if refused:
        raise HTTPForbidden(refused)

    setattr(removal, f'{side}_validated_by', user_id)
    setattr(removal, f'{side}_validated_at', func.now())
    _log(removal, ACTION_VALIDATE, user_id, side=side)
    return _answer(request, removal)


@write(
    validators=[validate_id, body_validator(UnvalidateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def unvalidate_removal_request(request):
    """Cancel the validation of a side of a removal request.

    The moderator gives the forum discussion in which the cancellation is
    explained. The previous discussions stay in the history.

    Request:
        `POST` `/users/removals/{id}/unvalidate`

    Request body:
        {'side': 'topoguide' | 'forum', 'forum_url': '...'}
    """
    side = request.validated['side']
    _check_side(request, side)
    removal = _get_request(request.validated['id'])
    _check_open(removal)

    if getattr(removal, f'{side}_validated_by') is None:
        raise HTTPBadRequest(f'The request is not validated by the {side}')

    setattr(removal, f'{side}_validated_by', None)
    setattr(removal, f'{side}_validated_at', None)
    removal.forum_url = request.validated['forum_url']
    _log(
        removal,
        ACTION_UNVALIDATE,
        request.authenticated_userid,
        side=side,
        forum_url=removal.forum_url,
    )
    return _answer(request, removal)


@write(
    validators=[validate_id, body_validator(ForumUrlSchema)],
    permission='authenticated',
    json=True,
)
def update_removal_request(request):
    """Change the forum discussion of a request being in progress.

    Request:
        `PUT` `/users/removals/{id}`

    Request body:
        {'forum_url': '...'}
    """
    roles = _check_moderator(request)
    removal = _get_request(request.validated['id'])
    if removal.status != STATUS_IN_PROGRESS:
        raise HTTPBadRequest('Only a request in progress can be changed')

    removal.forum_url = request.validated['forum_url']
    _log(
        removal,
        ACTION_UPDATE,
        request.authenticated_userid,
        forum_url=removal.forum_url,
    )
    return _answer(request, removal, roles)


@write(
    validators=[validate_id, body_validator(ForumUrlSchema)],
    permission='authenticated',
    json=True,
)
def cancel_removal_request(request):
    """Cancel a removal request, which is not done yet.

    The moderator gives the forum discussion in which the cancellation is
    explained. The request is kept, cancelled; a new one can be made.

    Request:
        `POST` `/users/removals/{id}/cancel`

    Request body:
        {'forum_url': '...'}
    """
    roles = _check_moderator(request)
    removal = _get_request(request.validated['id'])
    _check_open(removal)

    user_id = request.authenticated_userid
    removal.cancelled_by = user_id
    removal.cancelled_at = func.now()
    removal.forum_url = request.validated['forum_url']
    _log(removal, ACTION_CANCEL, user_id, forum_url=removal.forum_url)
    return _answer(request, removal, roles)
