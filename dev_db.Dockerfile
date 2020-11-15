FROM docker.io/c2corg/c2corg_pgsql:anon-2018-11-02

RUN apt-get update
RUN apt-get -y --no-install-recommends install sudo

RUN export PGDATA=/c2corg_anon
COPY ./docker-compose/pgsql-settings.d/ /c2corg_anon/pgsql-settings.d/

COPY ./ /v6_api/
