"""The requests to anonymize, merge or delete a user account.

A moderator (of the topoguide or of the forum) makes a request. It must then be
validated by a moderator of the topoguide and by a moderator of the forum: three
different persons. The account is removed afterwards by the script
`c2corg_api/scripts/users/process_removals.py`, once the date of the request is
past.
"""

import datetime
import logging

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
    REASONS,
    SIDE_FORUM,
    SIDE_TOPOGUIDE,
    SIDES,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    AccountRemovalRequest,
)
from c2corg_api.models.user import User
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Date, Int, OneOf, Str
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.resource import write

log = logging.getLogger(__name__)


class CreateRemovalSchema(Schema):
    user_id: Int
    reason: OneOf(REASONS)
    executable_after: Date
    target_user_id: Int
    target_forum_id: Int
    forum_url: Str(500) = None


class RemovalIdSchema(Schema):
    id: Int


class ValidateRemovalSchema(Schema):
    id: Int
    side: OneOf(SIDES)


class UnvalidateRemovalSchema(Schema):
    id: Int
    side: OneOf(SIDES)
    # the discussion in which the validation is questioned
    forum_url: Str(500)


class UpdateRemovalSchema(Schema):
    id: Int
    forum_url: Str(500)


def _is_forum_moderator(request, strict=False):
    """Tell whether the authenticated user is a moderator of the forum.

    If the forum does not answer, the user is considered as not being one,
    unless `strict` (the check protects an action): the action is then refused.
    """
    user_id = request.authenticated_userid
    try:
        client = get_discourse_client(request.registry.settings)
        return bool(client.is_moderator(user_id))
    except Exception as e:
        log.error('Checking the Discourse moderator failed: %d', user_id, exc_info=True)
        if strict:
            raise HTTPServiceUnavailable(
                'Checking the moderators of the forum failed'
            ) from e
        return False


def _check_side(request, side):
    """Check that the authenticated user is a moderator of the side."""
    if side == SIDE_TOPOGUIDE:
        allowed = request.has_permission('moderator')
    else:
        allowed = _is_forum_moderator(request, strict=True)
    if not allowed:
        raise HTTPForbidden(f'You are not a moderator of the {side}')


def _check_moderator(request):
    """Return the roles (topoguide, forum) of the user, who has at least one."""
    topoguide = bool(request.has_permission('moderator'))
    # a moderator of the topoguide is not blocked by a forum which is down
    forum = _is_forum_moderator(request, strict=not topoguide)
    if not topoguide and not forum:
        raise HTTPForbidden('Only the moderators can manage the removal requests')
    return topoguide, forum


def _get_request(request_id):
    removal = DBSession.get(AccountRemovalRequest, request_id)
    if not removal:
        raise HTTPNotFound(f'Unknown removal request {request_id}')
    return removal


def _not_done(removal):
    if removal.status == STATUS_DONE:
        raise HTTPBadRequest('The account has already been removed')


def _serialize_all(removals):
    ids = set()
    for removal in removals:
        ids.update(
            user_id
            for user_id in (
                removal.requested_by,
                removal.topoguide_validated_by,
                removal.forum_validated_by,
            )
            if user_id is not None
        )
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
            'done_at': iso(removal.done_at),
            'status': removal.status,
        }
        for removal in removals
    ]


def read_removal_requests(request):
    """Get the removal requests, the open ones first.

    Request:
        `GET` `/users/removals`

    Example response:

        {
            'removals': [{'id': 1, 'user_id': 123, 'status': 'in_progress', ...}],
            'roles': {'topoguide': true, 'forum': false}
        }
    """
    topoguide, forum = _check_moderator(request)
    removals = (
        DBSession.query(AccountRemovalRequest)
        .order_by(
            AccountRemovalRequest.done_at.is_not(None),
            AccountRemovalRequest.created_at.desc(),
        )
        .all()
    )
    return {
        'removals': _serialize_all(removals),
        'roles': {SIDE_TOPOGUIDE: topoguide, SIDE_FORUM: forum},
    }


def read_removal_requests_count(request):
    """Get the number of removal requests not done yet.

    Request:
        `GET` `/users/removals/count`

    Example response:

        {'open': 2}

    Like the list, it is for the moderators of the topoguide and of the forum.
    """
    _check_moderator(request)
    count = (
        DBSession.query(func.count(AccountRemovalRequest.id))
        .filter(AccountRemovalRequest.done_at.is_(None))
        .scalar()
    )
    return {'open': count}


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
            'target_user_id': @user_id@,
            'target_forum_id': @forum_user_id@,
            'forum_url': 'https://forum...'   # optional
        }
    """
    _check_moderator(request)
    validated = request.validated
    user_id = validated['user_id']
    target_user_id = validated['target_user_id']

    if user_id == target_user_id:
        raise HTTPBadRequest('The account cannot be merged into itself')

    user = DBSession.get(User, user_id)
    if not user:
        raise HTTPBadRequest(f'Unknown user {user_id}')
    if user.moderator:
        raise HTTPBadRequest('A moderator account cannot be removed')
    if not DBSession.get(User, target_user_id):
        raise HTTPBadRequest(f'Unknown user {target_user_id}')

    if validated['executable_after'] < datetime.datetime.now(datetime.UTC).date():
        raise HTTPBadRequest('The date of the removal cannot be in the past')

    open_request = (
        DBSession.query(AccountRemovalRequest.id)
        .filter(
            AccountRemovalRequest.user_id == user_id,
            AccountRemovalRequest.done_at.is_(None),
        )
        .first()
    )
    if open_request:
        raise HTTPConflict(f'The user {user_id} already has a removal request')

    forum_id = None
    try:
        forum_id = get_discourse_client(request.registry.settings).get_userid(user_id)
    except Exception:
        # the forum account is searched again when the account is removed
        log.warning('Finding the forum account failed: %d', user_id, exc_info=True)

    removal = AccountRemovalRequest(
        user_id=user_id,
        forum_id=forum_id,
        user_name=user.name,
        user_forum_username=user.forum_username,
        reason=validated['reason'],
        executable_after=validated['executable_after'],
        target_user_id=target_user_id,
        target_forum_id=validated['target_forum_id'],
        forum_url=validated.get('forum_url'),
        requested_by=request.authenticated_userid,
    )
    DBSession.add(removal)
    DBSession.flush()
    DBSession.refresh(removal)
    return _serialize_all([removal])[0]


@write(
    validators=[body_validator(ValidateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def validate_removal_request(request):
    """Validate a removal request, as a moderator of the topoguide or the forum.

    The author of the request cannot validate it, and nobody can validate both
    sides of it.

    Request:
        `POST` `/users/removals/validate`

    Request body:
        {'id': @request_id@, 'side': 'topoguide' | 'forum'}
    """
    side = request.validated['side']
    removal = _get_request(request.validated['id'])
    _not_done(removal)
    _check_side(request, side)

    user_id = request.authenticated_userid
    if removal.requested_by == user_id:
        raise HTTPForbidden('The author of a request cannot validate it')

    other_side = SIDE_FORUM if side == SIDE_TOPOGUIDE else SIDE_TOPOGUIDE
    if getattr(removal, f'{side}_validated_by') is not None:
        raise HTTPConflict(f'The request is already validated by the {side}')
    if getattr(removal, f'{other_side}_validated_by') == user_id:
        raise HTTPForbidden('Only one side of a request can be validated by a person')

    setattr(removal, f'{side}_validated_by', user_id)
    setattr(removal, f'{side}_validated_at', func.now())
    DBSession.flush()
    DBSession.refresh(removal)
    return _serialize_all([removal])[0]


@write(
    validators=[body_validator(UnvalidateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def unvalidate_removal_request(request):
    """Cancel the validation of a side of a removal request.

    The moderator gives the forum discussion in which the cancellation is
    explained.

    Request:
        `POST` `/users/removals/unvalidate`

    Request body:
        {'id': @request_id@, 'side': 'topoguide' | 'forum', 'forum_url': '...'}
    """
    side = request.validated['side']
    removal = _get_request(request.validated['id'])
    _not_done(removal)
    _check_side(request, side)

    if getattr(removal, f'{side}_validated_by') is None:
        raise HTTPBadRequest(f'The request is not validated by the {side}')

    setattr(removal, f'{side}_validated_by', None)
    setattr(removal, f'{side}_validated_at', None)
    removal.forum_url = request.validated['forum_url']
    DBSession.flush()
    return _serialize_all([removal])[0]


@write(
    validators=[body_validator(UpdateRemovalSchema)],
    permission='authenticated',
    json=True,
)
def update_removal_request(request):
    """Change the forum discussion of a request being in progress.

    Request:
        `POST` `/users/removals/update`

    Request body:
        {'id': @request_id@, 'forum_url': '...'}
    """
    _check_moderator(request)
    removal = _get_request(request.validated['id'])
    if removal.status != STATUS_IN_PROGRESS:
        raise HTTPBadRequest('Only a request in progress can be changed')

    removal.forum_url = request.validated['forum_url']
    DBSession.flush()
    return _serialize_all([removal])[0]


@write(
    validators=[body_validator(RemovalIdSchema)],
    permission='authenticated',
    json=True,
)
def cancel_removal_request(request):
    """Cancel a removal request, which is not done yet.

    Request:
        `POST` `/users/removals/cancel`

    Request body:
        {'id': @request_id@}
    """
    _check_moderator(request)
    removal = _get_request(request.validated['id'])
    _not_done(removal)

    DBSession.delete(removal)
    return {}
