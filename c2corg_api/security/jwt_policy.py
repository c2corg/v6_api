from pyramid_jwt import JWTAuthenticationPolicy


class IntegerSubJWTAuthenticationPolicy(JWTAuthenticationPolicy):
    """Custom JWT authentication policy that converts the ``sub`` claim
    back to an integer so that the rest of the application can keep
    comparing ``request.authenticated_userid`` with integer user ids.

    PyJWT >= 2.9 enforces that ``sub`` must be a string (per the JWT
    spec), but this application has historically stored integer user ids
    in the ``sub`` claim.  We now encode ``sub`` as a string (see
    :func:`c2corg_api.security.roles.create_claims`) and convert it
    back here.
    """

    def unauthenticated_userid(self, request):
        sub = request.jwt_claims.get('sub')
        if sub is not None:
            try:
                return int(sub)
            except (TypeError, ValueError):
                return sub
        return None
