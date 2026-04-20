"""
FastAPI User Profile router.

Handles GET (single + collection), PUT, and document info for user profiles.
User profiles are created automatically when a user registers — there is
no POST endpoint.

During the transition both this router **and** the legacy
``c2corg_api.views.user_profile.UserProfileRest`` coexist.  The FastAPI
routes are served under ``/v2/profiles`` so that the legacy ``/profiles``
Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session, joinedload, load_only

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile
from c2corg_api.models.user_profile import attributes as profile_attributes
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import user_profile_documents_config
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
)
from c2corg_api.schemas.user_profile import (
    UpdateUserProfileSchema,
    UserProfileReadSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/profiles', tags=['profiles'])

# User profiles only require locales on update (no title check — it's reset).
REQUIRED_FIELDS = ['locales']


# ──────────────────────────────────────────────────────────────────────
# GET collection  — /v2/profiles
# ──────────────────────────────────────────────────────────────────────


@router.get('')
def get_profiles(
    request: Request,
    q: CollectionParams = Depends(),
    user: User = Depends(get_current_user),
):
    """Return a paginated list of user profiles.

    Requires authentication (same as the Pyramid ``restricted_view``).
    """
    return get_document_collection(
        user_profile_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────────────
# GET single  — /v2/profiles/{id}
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_profile(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
    user: User | None = Depends(get_optional_current_user),
):
    """Return a single user profile.

    * If the profile is **public** or the requester is **authenticated**
      → full profile.
    * Otherwise → only ``{not_authorized, document_id, name}``.
    * Unconfirmed users (email not validated) → 404.
    """
    db = q.db

    # Load the user row to check visibility
    requested_user = (
        db.query(User)
        .filter(User.id == document_id)
        .filter(User.email_validated)
        .options(load_only(User.id, User.is_profile_public, User.name))
        .first()
    )

    if not requested_user:
        raise HTTPException(status_code=404, detail='user not found')

    if requested_user.is_profile_public or user is not None:
        # Full profile — eagerly load the User relationship so that
        # the ``name`` / ``forum_username`` association proxies survive
        # the ``db.expunge()`` that happens during locale selection.
        return get_single_document(
            UserProfile,
            document_id,
            document_type=USERPROFILE_TYPE,
            lang=q.lang,
            editing_view=q.editing_view,
            cook=q.cook,
            read_schema=UserProfileReadSchema,
            include_areas=True,
            extra_query_options=[joinedload(UserProfile.user)],
            request=request,
            response=response,
            db=db,
        )
    else:
        # Private profile, unauthenticated → minimal info only
        return {
            'not_authorized': True,
            'document_id': requested_user.id,
            'name': requested_user.name,
        }


# ──────────────────────────────────────────────────────────────────────
# PUT  — /v2/profiles/{id}
# ──────────────────────────────────────────────────────────────────────


def _reset_title(document, doc_schema):
    """User profile documents have no meaningful title.

    The title column is NOT NULL, so we silently set it to ``''``.
    This is the ``before_update`` callback — receives the SA document
    and the validated Pydantic schema.
    """
    if doc_schema.locales:
        for locale in doc_schema.locales:
            locale.title = ''


@router.put('/{document_id}', status_code=200)
def update_profile(
    document_id: DocumentId,
    body: UpdateUserProfileSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing user profile.

    Only the profile owner or a moderator may update a profile.
    """
    if not user.moderator:
        if user.id != document_id:
            raise HTTPException(
                status_code=403, detail='No permission to change this user profile'
            )

    return update_document(
        document_id=document_id,
        model_class=UserProfile,
        body_schema=body,
        document_type=USERPROFILE_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=profile_attributes,
        user=user,
        db=db,
        before_update=_reset_title,
    )


# ──────────────────────────────────────────────────────────────────────
# GET info — /v2/profiles/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_profile_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        UserProfile, document_id, lang, request=request, response=response, db=db
    )
