from c2corg_api import DBSession
from c2corg_api.models.common.attributes import mailinglists as valid_mailinglists
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.user import User
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import restricted_json_view, restricted_view
from c2corg_api.views.resource import resource


def validate_mailinglist_statuses(request, **kwargs):
    mailinglists = {}
    data = request.json_body
    for ml in data:
        if ml not in valid_mailinglists:
            request.errors.add('body', ml, f'Mailing list `{ml}` does not exist')
        elif not isinstance(data[ml], bool):
            request.errors.add(
                'body',
                ml,
                f'Status `{data[ml]}` of mailing list `{ml}` should be boolean',
            )
        else:
            mailinglists[ml] = data[ml]
    request.validated['mailinglists'] = mailinglists


@resource(path='/users/mailinglists')
class UserMailinglistsRest(ACLDefault):
    @restricted_view()
    def get(self):
        """Get the mailinglists subscriptions of the authenticated user.

        Request:
            `GET` `/users/mailinglists`

        Example response:

            {'avalanche': False, 'lawinen': True, 'valanghe': False, ...}

        """
        user_id = self.request.authenticated_userid
        res = (
            DBSession.query(Mailinglist.listname)
            .filter(Mailinglist.user_id == user_id)
            .all()
        )
        subscribed_mailinglists = [list[0] for list in res]

        return {ml: ml in subscribed_mailinglists for ml in valid_mailinglists}

    @restricted_json_view(validators=[validate_mailinglist_statuses])
    def post(self):
        """Update mailinglist subscription statuses.

        Request:
            `POST` `/users/mailinglists`
            {'avalanche': False, 'lawinen': True, 'valanghe': False}

        """
        user_id = self.request.authenticated_userid
        user = DBSession.get(User, user_id)

        subscribed_lists = (
            DBSession.query(Mailinglist).filter(Mailinglist.user_id == user_id).all()
        )
        subscribed_lists = {list.listname: list for list in subscribed_lists}
        subscribed_listnames = set(subscribed_lists.keys())

        lists_to_add = []
        removed_lists = False
        data = self.request.validated['mailinglists']
        for listname in data:
            subscribe_status = data.get(listname, False)
            if subscribe_status and listname not in subscribed_listnames:
                # Add list
                lists_to_add.append(
                    Mailinglist(
                        listname=listname, email=user.email, user_id=user_id, user=user
                    )
                )
            elif not subscribe_status and listname in subscribed_listnames:
                # Remove list
                removed_lists = True
                DBSession.delete(subscribed_lists[listname])

        if lists_to_add:
            DBSession.add_all(lists_to_add)
        if lists_to_add or removed_lists:
            DBSession.flush()
        return {}
