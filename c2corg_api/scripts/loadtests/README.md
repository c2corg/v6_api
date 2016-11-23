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
    sudo -u postgres psql <dbname> -c "select document_id || ',' || lang as data from guidebook.outings join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > outings.csv
    sudo -u postgres psql <dbname> -c "select document_id || ',' || lang as data from guidebook.routes join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > routes.csv
    sudo -u postgres psql <dbname> -c "select document_id || ',' || lang as data from guidebook.waypoints join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > waypoints.csv


A few simple manual changes are then required to make the generated files valid CSV files for Gatling's feeders:
* replace `data` by `id,lang`
* remove the extra lines with no data
* remove the first blank column

Creating a list of test usernames and passwords
-----------------------------------------------

Run:

    cd gatling/user-files/data
    sh users.sh > users.csv
