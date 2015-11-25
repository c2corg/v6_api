from pyramid.view import view_config
from c2corg_api.security.roles import try_login, remove_token

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

    token = try_login(user, password, request)
    if token:
        return {
            'token': token
        }
    else:
        return {
            'error': 'login failed'
        }
