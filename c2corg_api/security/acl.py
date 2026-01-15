from pyramid.security import Allow, Everyone, Authenticated

__all__ = ["ACLDefault"]


class ACLDefault:
    @staticmethod
    def __acl__():
        return [
            (Allow, Everyone, 'public'),
            (Allow, Authenticated, 'authenticated'),
            (Allow, 'group:moderators', 'moderator')
        ]

    def __init__(self, request, context=None, **kwargs):
        self.request = request
        self.context = context
