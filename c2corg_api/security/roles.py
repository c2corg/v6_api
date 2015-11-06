from pyramid.security import Authenticated

# This hardcoded data will be removed when we have user table
USERS = {
        'guillaume': 'guipass',
        'jack': 'guesspass'
}

GROUPS = {
        'guillaume': ['group:admins'],
        'jack': [Authenticated]
}

TOKENS = set()


def groupfinder(userid, request):
    if userid in USERS:
        return GROUPS.get(userid, [])


def validate_token(request, token):
    return token in TOKENS


def add_token(token):
    TOKENS.add(token)


def remove_token(token):
    if token in TOKENS:
        TOKENS.remove(token)
