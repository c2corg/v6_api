FROM docker.io/c2corg/c2corg_pgsql:anon-2018-11-02

RUN apt-get update
RUN apt-get -y --no-install-recommends install sudo

RUN export PGDATA=/c2corg_anon
COPY ./docker-compose/pgsql-settings.d/ /c2corg_anon/pgsql-settings.d/

COPY ./ /v6_api/

# HOW to run a script on db in docker file ?????????

# ADD ./scripts/create_user_db_test.sh /docker-entrypoint-initdb.d/ZZZ-06-create-user-db-test.sh

# RUN sudo service postgresql start
# RUN while !</dev/tcp/db/5432; do sleep 1; echo 'Wait'; done;
# RUN /v6_api/scripts/create_user_db_test.sh
# RUN sudo service postgresql stop

