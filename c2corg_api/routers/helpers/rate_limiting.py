"""
FastAPI rate-limiting logic.

Port of the Pyramid tween ``c2corg_api.tweens.rate_limiting``.
The logic is identical:

* Only write requests (POST, PUT, DELETE) are rate-limited.
* Each user has a sliding window stored on their ``User`` row
  (``ratelimit_reset``, ``ratelimit_remaining``).
* When the window is exhausted a **429 Too Many Requests** is raised.
* Repeated rate-limit violations cause the user to be **blocked**
  (``user.blocked = True``).
* An alert e-mail is sent to moderators on each violation.

Called from ``get_current_user`` — no separate dependency needed.
"""

import logging
from datetime import datetime, timedelta, timezone
from smtplib import SMTPAuthenticationError

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from c2corg_api.emails.email_service import get_email_service_from_settings
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

# ── Module-level settings cache ──────────────────────────────────
# Populated once at startup by ``configure_rate_limiting()``.
_settings: dict = {}


def configure_rate_limiting(settings: dict) -> None:
    """Called once at startup from ``create_app()``."""
    global _settings
    _settings = settings


def _user_limit(user: User) -> int:
    """Return the per-window request limit for *user*."""
    if user.robot:
        return int(_settings.get('rate_limiting.limit_robot', 1000))
    if user.moderator:
        return int(_settings.get('rate_limiting.limit_moderator', 100))
    return int(_settings.get('rate_limiting.limit', 50))


def check_rate_limit(user: User, request: Request, db: Session) -> None:
    """Apply rate-limiting to *user* for a write request.

    Modifies ``user`` in-place (same SA session as the caller) and
    raises ``HTTPException(429)`` when the limit is exceeded.

    When the limit is hit the counter updates are committed **before**
    raising so that ``get_db``'s rollback-on-exception does not
    discard them (mirrors the Pyramid tween which returns an error
    *response* and lets ``pyramid_tm`` commit normally).

    No-op for non-write methods (GET, HEAD, OPTIONS, …).
    """
    if request.method not in ('POST', 'PUT', 'DELETE'):
        return

    window_span = int(_settings.get('rate_limiting.window_span', 900))
    max_times = int(_settings.get('rate_limiting.max_times', 3))
    now = datetime.now(timezone.utc)

    if user.ratelimit_reset is None or user.ratelimit_reset < now:
        # No window or expired → create a new one.
        limit = _user_limit(user)
        user.ratelimit_reset = now + timedelta(seconds=window_span)
        user.ratelimit_remaining = limit - 1
        log.debug('RATE LIMITING, CREATE WINDOW SPAN : %s', user.ratelimit_reset)
        return

    if user.ratelimit_remaining:
        user.ratelimit_remaining -= 1
        log.info(
            'RATE LIMITING, REQUESTS REMAINING FOR %s : %s',
            user.id,
            user.ratelimit_remaining,
        )
        return

    # User is rate-limited.
    log.warning('RATE LIMIT REACHED FOR USER %s', user.id)

    current_window = user.ratelimit_reset
    if user.ratelimit_last_blocked_window != current_window:
        user.ratelimit_last_blocked_window = current_window
        user.ratelimit_times += 1

        if user.ratelimit_times > max_times:
            log.warning('RATE LIMIT BLOCK USER %s', user.id)
            user.blocked = True

        # Alert moderators
        try:
            email_service = get_email_service_from_settings(_settings)
            email_service.send_rate_limiting_alert(user)
        except SMTPAuthenticationError:
            log.error('RATE LIMIT ALERT MAIL : AUTHENTICATION ERROR')

    # Commit counter updates before raising so they survive
    # get_db's rollback-on-exception.  The Pyramid tween achieves
    # the same by returning an error *response* (letting pyramid_tm
    # commit); here we must commit explicitly before raising.
    db.commit()
    raise HTTPException(status_code=429, detail='Rate limit reached')
