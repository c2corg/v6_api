from c2corg_api.security.discourse_client import (
    discourse_get_username_by_userid, get_discourse_client)

from cornice.resource import resource

from c2corg_api.views import cors_policy, restricted_view

import colander
import logging
log = logging.getLogger(__name__)


class PrivateMessageRequestMapping(colander.MappingSchema):
    kind = colander.SchemaNode(
            colander.String(),
            name='kind',
            default='all',
            validator=colander.OneOf(['all', 'unread']))


@resource(path='/forum/private-messages', cors_policy=cors_policy)
class PrivateMessageRest(object):
    def __init__(self, request):
        self.request = request

    @restricted_view(renderer='json', schema=PrivateMessageRequestMapping())
    def post(self):
        request = self.request
        client = get_discourse_client(request.registry.settings)
        userid = request.authenticated_userid
        d_username = discourse_get_username_by_userid(client, userid)
        if request.validated['kind'] == 'all':
            return client.private_messages(d_username)
        else:
            return client.private_messages_unread(d_username)
