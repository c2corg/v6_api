from c2corg_api.security.discourse_client import (
    discourse_get_username_by_userid, get_discourse_client,
    get_discourse_public_url)

from cornice.resource import resource

from c2corg_api.views import cors_policy, restricted_view


@resource(path='/forum/private-messages/unread-count', cors_policy=cors_policy)
class PrivateMessageRest(object):
    def __init__(self, request):
        self.request = request

    @restricted_view(renderer='json')
    def get(self):
        settings = self.request.registry.settings
        userid = self.request.authenticated_userid

        client = get_discourse_client(settings)
        d_username = discourse_get_username_by_userid(client, userid)
        messages = client.private_messages_unread(d_username)

        count = len(messages['topic_list']['topics'])
        link = '%s/users/%s/messages' % (
            get_discourse_public_url(settings), d_username)

        return {link: link, count: count}
