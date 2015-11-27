from pyramid.view import view_config
from c2corg_api.security.roles import remove_token


@view_config(route_name='logout', renderer='json', permission='authenticated')
def logout(request):
    result = {'user': request.authenticated_userid}
    remove_token(request.authorization[1][7:-1])
    return result


@view_config(route_name='check_token', renderer='json')
def token_permissions(request):
    return {'user': request.authenticated_userid}
