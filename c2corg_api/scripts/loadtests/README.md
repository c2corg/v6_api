Tools for load testing with Gatling
===================================

Load tests are done using [Gatling](http://gatling.io/).

Adding test user accounts
-------------------------

This script creates 1000 user accounts with usernames/passwords of the form
`testuserc2c<1 to 1000>`.

Run:

    .build/venv/bin/python c2corg_api/scripts/loadtests/create_test_users.py


Creating lists of document URLs
-------------------------------

Run:

    sudo -u postgres psql <dbname> -c "select '/outings/' || document_id || '/' || lang || '/foo' as url from guidebook.outings join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > outing_urls.csv
    sudo -u postgres psql <dbname> -c "select '/routes/' || document_id || '/' || lang || '/foo' as url from guidebook.routes join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > route_urls.csv
    sudo -u postgres psql <dbname> -c "select '/waypoints/' || document_id || '/' || lang || '/foo' as url from guidebook.waypoints join guidebook.documents_locales using (document_id) order by document_id desc limit 100;" > waypoint_urls.csv


A few simple manual changes are then required to make the generated files valid CSV files for Gatling's feeders.

Creating a list of test usernames and passwords
-----------------------------------------------

Run:

    cd files
    sh users_list.sh > users.csv
