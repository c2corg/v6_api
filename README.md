API Application for camptocamp.org v6
=====================================

Checkout
--------

    git clone https://github.com/c2corg/v6_api.git

Build
-----

    cd v6_api
    make -f config/{user} install

To set up the database
----------------------

    scripts/create_user_db.sh

If you want to specify a specific string as user, you can instead use:

    USER=something scripts/create_user_db.sh

To set up ElasticSearch
----------------------

    .build/venv/bin/initialize_c2corg_api_es development.ini

Run the application
-------------------

The API consists of three applications, the actual web-application, a syncer script
that synchronizes the database with ElasticSearch and a background jobs script that
purges the database of non activated accounts and expired tokens. The three have to
be started separately.

To start the background jobs script (run-background-jobs-prod for production):

    make -f config/$USER run-background-jobs

To start the syncer script (run-syncher-prod for production):

    make -f config/$USER run-syncer

To start the web-application:

    make -f config/$USER serve

Open your browser at http://localhost:6543/ or http://localhost:6543/?debug (debug mode). Make sure you are
using the port that is set in `config/$USER`.

Available actions may be listed using:

    make help

Requests examples
-----------------

Get the list of waypoints:

    GET http://localhost:6543/waypoints

Get waypoint with id=1:

    GET http://localhost:6543/waypoints/1

Insert a waypoint:

    curl -X POST -v \
    -H "Content-Type: application/json" \
    -d '{"waypoint_type": "summit", "elevation": 3779, "geometry": {"geom": "{\"type\": \"Point\", \"coordinates\": [635956, 5723604]}"},"locales": [{"lang": "fr", "title": "Mont Pourri"}]}' \
    http://localhost:6543/waypoints

Updating a waypoint:

    curl -X PUT -v \
    -H "Content-Type: application/json" \
    -d '{"message": "Comment about change", "document": {"elevation": 4633, "maps_info": null, "version": 1, "document_id": 1, "waypoint_type": "summit", "locales": [{"lang": "fr", "version": 1, "title": "Mont Rose", "access": null, "description": null}]}}' \
    http://localhost:6543/waypoints/1

API documentation
-----------------

- [Simple search](./c2corg_api/views/search.py)
- [Guidebook API](./c2corg_api/views/waypoint.py)

Forum integration (discourse)
--------------------------

See https://github.com/c2corg/v6_forum


Run the tests
--------------

Create a database that will be used to run the tests:

    scripts/create_user_db_test.sh

If you want to specify a specific string as user you can instead enter:

    USER=something scripts/create_user_db_test.sh

Then run the tests with:

    make -f config/$USER test
    
Or with the `check` target, which runs `flake8` and `test`:

    make -f config/$USER check

To run a specific test:

    .build/venv/bin/nosetests c2corg_api/tests/views/test_waypoint.py
    .build/venv/bin/nosetests -s  c2corg_api/tests/views/test_waypoint.py:TestWaypointRest.test_get_lang

To see the debug output:

    .build/venv/bin/nosetests -s


Production checks
-----------------

Check the Discourse forum is up and available to the client API:
  
    scripts/check_discourse_connection.sh [id]

"id" is a v6 user id. The script should return a 200OK.


Developer Tips
--------------

The API is mainly built using the following components:
* Pyramid (Python framework) http://docs.pylonsproject.org/en/latest/
* SQLAlchemy (ORM) http://docs.sqlalchemy.org/en/rel_1_0/
* Cornice (REST framework) https://cornice.readthedocs.org/en/latest/
* Colander (validating and deserializing data) http://docs.pylonsproject.org/projects/colander/en/latest/

