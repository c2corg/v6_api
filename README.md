API Application for v6
======================

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
    \c c2corg_{user}_tests
    create extension postgis;
    create schema topoguide authorization "www-data";
    \q
    .build/venv/bin/initialize_app_api_db development.ini

Run the application
-------------------

    make -f config/{user} serve

Open your browser at http://localhost:6543/ or http://localhost:6543/?debug (debug mode). Make sure you are
using the port that is set in `config/{user}`.

Available actions may be listed using:

    make help

Run the tests
--------------
Create a database that will be used to run the tests:

    psql
    create database c2corg_{user}_tests owner "www-data";
    \c c2corg_{user}_tests
    create extension postgis;
    create schema topoguide authorization "www-data";
    \q

Then run the tests with:

    make -f config/{user} test
    
Or with the `check` target, which runs `flake8` and `test`:

    make -f config/{user} check

To run a specific test:

    .build/venv/bin/nosetests app_api/tests/views/test_summit.py

To see the debug output:

    .build/venv/bin/nosetests -s
