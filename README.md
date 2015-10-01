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

    psql
    create database c2corg_{user} owner "www-data";
    \c c2corg_{user}
    create extension postgis;
    create schema guidebook authorization "www-data";
    \q
    .build/venv/bin/initialize_c2corg_api_db development.ini

Run the application
-------------------

    make -f config/{user} serve

Open your browser at http://localhost:6543/ or http://localhost:6543/?debug (debug mode). Make sure you are
using the port that is set in `config/{user}`.

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
    -d '{"waypoint_type": "summit", "elevation": 3779, "locales": [{"culture": "fr", "title": "Mont Pourri"}]}' \
    http://localhost:6543/waypoints

Updating a waypoint:

    curl -X PUT -v \
    -H "Content-Type: application/json" \
    -d '{"message": "Comment about change", "document": {"elevation": 4633, "maps_info": null, "version": "fae1e03a38c344218db13cb224d839e7", "document_id": 1, "waypoint_type": "summit", "locales": [{"culture": "fr", "version": "ca9797ea19334fa3a99127bf00d39410", "title": "Mont Rose", "pedestrian_access": null, "description": null}]}}' \
    http://localhost:6543/waypoints/1

Run the tests
--------------
Create a database that will be used to run the tests:

    psql
    create database c2corg_{user}_tests owner "www-data";
    \c c2corg_{user}_tests
    create extension postgis;
    create schema guidebook authorization "www-data";
    \q

Then run the tests with:

    make -f config/{user} test
    
Or with the `check` target, which runs `flake8` and `test`:

    make -f config/{user} check

To run a specific test:

    .build/venv/bin/nosetests c2corg_api/tests/views/test_summit.py

To see the debug output:

    .build/venv/bin/nosetests -s

Developer Tips
--------------

The API is mainly built using the following components:
* Pyramid (Python framework) http://docs.pylonsproject.org/en/latest/
* SQLAlchemy (ORM) http://docs.sqlalchemy.org/en/rel_1_0/
* Cornice (REST framework) https://cornice.readthedocs.org/en/latest/
* Colander (validating and deserializing data) http://docs.pylonsproject.org/projects/colander/en/latest/

