import re

from pyramid_jwt import JWTAuthenticationPolicy

# Matches token="<value>" in the Authorization header params
_TOKEN_RE = re.compile(r'token="([^"]+)"')


class IntegerSubJWTAuthenticationPolicy(JWTAuthenticationPolicy):
    """Custom JWT authentication policy that handles the legacy
    ``JWT token="<token>"`` header format used by the frontend,
    and converts the ``sub`` claim back to an integer so that the
    rest of the application can keep comparing
    ``request.authenticated_userid`` with integer user ids.

    PyJWT >= 2.9 enforces that ``sub`` must be a string (per the JWT
    spec), but this application has historically stored integer user ids
    in the ``sub`` claim.  We now encode ``sub`` as a string (see
    :func:`c2corg_api.security.roles.create_claims`) and convert it
    back here.
    """

    def get_claims(self, request):
        """Extract claims from the request, supporting the legacy
        ``JWT token="<value>"`` authorization header format.
        """
        try:
            if request.authorization is None:
                return {}
        except ValueError:
            return {}
        (auth_type, params) = request.authorization
        if auth_type != self.auth_type:
            return {}
        # Support legacy format: JWT token="<actual_token>"
        match = _TOKEN_RE.search(params)
        token = match.group(1) if match else params
        if not token:
            return {}
        return self.jwt_decode(request, token)

    def unauthenticated_userid(self, request):
        sub = request.jwt_claims.get('sub')
        if sub is not None:
            try:
                return int(sub)
            except (TypeError, ValueError):
                return sub
        return None
