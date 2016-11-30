Tools for load testing with Gatling
===================================

Load tests are done using [Gatling](http://gatling.io/).

Using Gatling for load testing
------------------------------

* Download the [Gatling bundle](http://gatling.io/#/resources/download).
* Paste (or symlink) dir `gatling/user-files/` into the Gatling bundle.
* Read the [documentation](http://gatling.io/docs/2.2.3/quickstart.html#running-gatling).
* See also the [additional command line options](http://gatling.io/docs/2.2.3/general/configuration.html#command-line-options).

Run Gatling and choose what scenario to test (`users` is the number of concurrent users and `ramp` the time in seconds during which those users will be introduced):

    JAVA_OPTS="-Dusers=500 -Dramp=3600" bin/gatling.sh


Adding test user accounts
-------------------------

This script creates 1000 user accounts with usernames/passwords of the form
`testuserc2c<1 to 1000>`.

Run:

    .build/venv/bin/python c2corg_api/scripts/loadtests/create_test_users.py


Creating lists of document URLs
-------------------------------

Run:

    cd gatling/user-files/data
    psql -d <dbname> -A -F, -c "select document_id as id, lang as lang from guidebook.outings join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" | egrep -v '\(.*rows\)' > outings.csv
    psql <dbname> -A -F, -c "select document_id as id, lang as lang from guidebook.routes join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" | egrep -v '\(.*rows\)' > routes.csv
    psql <dbname> -A -F, -c "select document_id as id, lang as lang from guidebook.waypoints join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" | egrep -v '\(.*rows\)' > waypoints.csv

You might need to prefix these commands with on of these:
    sudo -u postgres
    docker -H $DOCKER_HOST exec -i -u postgres postgresql_postgresql_1

Creating a list of test usernames and passwords
-----------------------------------------------

Run:

    cd gatling/user-files/data
    sh users.sh > users.csv
