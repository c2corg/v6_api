User accounts scripts
=====================

This package contains the following scripts:
* `merge.py`: delete the source user account and reassign all its contributions and associations to the target user account.

Run accounts merging
--------------------

The script is run as a command line instruction:

    .build/venv/bin/python c2corg_api/scripts/users/merge.py <source id> <target id>

In a docker environment:

    docker-compose run --rm api .build/venv/bin/python c2corg_api/scripts/users/merge.py <source id> <target id>
