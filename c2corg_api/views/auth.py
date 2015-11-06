from pyramid.view import view_config
from pyramid.interfaces import IAuthenticationPolicy
from c2corg_api.security.roles import USERS, add_token, remove_token

import datetime
import json


@view_config(route_name='logout', renderer='json', permission='authenticated')
def logout(request):
    result = {'user': request.authenticated_userid}
    remove_token(request.authorization[1][7:-1])
    return result


@view_config(route_name='check_token', renderer='json')
def token_permissions(request):
    return {'user': request.authenticated_userid}


@view_config(route_name='login', renderer='json')
def login(request):
    form = json.loads(request.body)
    user = form['username']
    password = form['password']

    if user and password and USERS.get(user) == password:
        policy = request.registry.queryUtility(IAuthenticationPolicy)
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(weeks=1)
        token = policy.encode_jwt(request, claims={
            'sub': user,
            'exp': exp
        })
        add_token(token)

        return {
            'token': token
        }
    else:
        return {
            'error': 'login failed'
        }
