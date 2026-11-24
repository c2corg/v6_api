"""The emails telling a user about the removal of their account.

An anonymization or a merge is announced when it is requested (`planned`),
then confirmed once done (`done`); a spammer gets none. A merge is told to
both accounts, once if they share their address. Only a validated address
gets one: an unvalidated one may not be the user's.
"""

import logging

from c2corg_api.emails.email_service import get_email_service_from_settings
from c2corg_api.models import DBSession
from c2corg_api.models.account_removal import REASON_ANONYMIZATION, REASON_MERGE
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

PLANNED = 'planned'
DONE = 'done'


def _forum_url(settings):
    return settings.get('discourse.public_url') or settings.get('discourse.url', '')


def removal_emails(removal, stage, settings):
    """Return the emails of a request: [(address, lang, key, values)]."""
    # read before the merge, which deletes the account and its address
    if removal.reason not in (REASON_ANONYMIZATION, REASON_MERGE):
        return []
    user = DBSession.get(User, removal.user_id)
    if user is None:
        return []
    target = DBSession.get(User, removal.target_user_id)
    accounts = [user]
    if removal.reason == REASON_MERGE and target is not None:
        accounts.append(target)

    key = f'account_{removal.reason}_{stage}'
    values = {
        'name': removal.user_name,
        'target': target.name if target is not None else '',
        'date': removal.executable_after.isoformat(),
        'forum': _forum_url(settings),
    }
    emails = []
    seen = set()
    for account in accounts:
        if not account.email_validated or not account.email:
            continue
        if account.email.lower() in seen:
            continue
        seen.add(account.email.lower())
        emails.append((account.email, account.lang, key, values))
    return emails


def send_removal_emails(removal_id, emails, settings):
    """Send the emails of a request; a failure is only logged."""
    # the removal is done, or the request saved, whether the email goes or not
    service = get_email_service_from_settings(settings)
    for address, lang, key, values in emails:
        try:
            service.send_account_removal(address, lang, key, values)
        except Exception:
            log.exception('Sending %s of the removal #%d failed', key, removal_id)
