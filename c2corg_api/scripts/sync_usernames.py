import os
import sys
import traceback
from datetime import datetime
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import get_discourse_client

from sqlalchemy import engine_from_config

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)

    client = get_discourse_client(settings)

    users = DBSession.query(User)
    total = users.count()

    current = 0
    errors = 0
    start_time = datetime.now()

    for user in users:
        try:
            assert client.client.sync_sso(
                sso_secret=client.sso_key,
                name=user.name,
                username=user.forum_username + '_tmp',
                email=user.email,
                external_id=user.id)
            assert client.sync_sso(user)

        except Exception as e:
            print("{} ERROR on {} ({})\n{}".format(
                datetime.now(),
                user.forum_username,
                current,
                traceback.format_exc()))
            errors += 1
            return

        current = current + 1
        if current % 10 == 0:
            print("{}/{} processed ({})"
                  .format(current,
                          total,
                          datetime.now() - start_time))

    print('Process finished with {} errors.'.format(errors))


if __name__ == "__main__":
    main()
