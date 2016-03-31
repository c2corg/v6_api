from pydiscourse.client import DiscourseClient

import logging
log = logging.getLogger(__name__)


# 10 seconds timeout for requests to discourse API
# Using a large value to take into account a possible slow restart (caching)
# of discourse.
CLIENT_TIMEOUT = 10


def get_discourse_base_url(settings):
    return settings['discourse.url']


def get_discourse_public_url(settings):
    return settings['discourse.public_url']


def get_discourse_client(settings):
    api_key = settings['discourse.api_key']
    url = get_discourse_base_url(settings)
    # system is a built-in user available in all discourse instances.
    return DiscourseClient(
        url, api_username='system', api_key=api_key, timeout=CLIENT_TIMEOUT)


discourse_userid_cache = {}
discourse_username_cache = {}  # are we guaranteed usernames can never change?


def discourse_get_userid_by_userid(client, userid):
    discourse_userid = discourse_userid_cache.get(userid)
    if not discourse_userid:
        discourse_user = client.by_external_id(userid)
        discourse_userid = discourse_user['id']
        discourse_userid_cache[userid] = discourse_userid
        discourse_username_cache[userid] = discourse_user['username']
    return discourse_userid


def discourse_get_username_by_userid(client, userid):
    discourse_username = discourse_username_cache.get(userid)
    if not discourse_username:
        discourse_user = client.by_external_id(userid)
        discourse_userid_cache[userid] = discourse_user['id']
        discourse_username = discourse_user['username']
        discourse_username_cache[userid] = discourse_username
    return discourse_username


def discourse_sync_sso(user, settings):
    key = str(settings.get('discourse.sso_secret'))  # must not be unicode
    client = get_discourse_client(settings)

    result = client.sync_sso(
        sso_secret=key,
        name=user.name,
        username=user.forum_username,
        email=user.email,
        external_id=user.id)
    if result:
        discourse_userid_cache[user.id] = result['id']
    return result


def discourse_logout(userid, settings):
    client = get_discourse_client(settings)
    discourse_userid = discourse_get_userid_by_userid(client, userid)
    client.log_out(discourse_userid)
    return discourse_userid
