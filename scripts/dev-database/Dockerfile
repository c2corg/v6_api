# Lightweight anonymized dev database: PostgreSQL 18 + PostGIS, restored at the first start.
#   docker build --build-arg DUMP=c2corg-dev.dump -t c2corg-dev-db .
FROM postgis/postgis:18-3.6

# The server of the initialization is stopped with a checkpoint after the restore: on a slow disk it takes
# more than the 60 s which pg_ctl waits by default, and the container then exits.
ENV PGCTLTIMEOUT=600

ARG DUMP=c2corg-dev.dump
COPY ${DUMP} /docker-entrypoint-initdb.d/c2corg-dev.dump
COPY restore-dev.sh /docker-entrypoint-initdb.d/20-restore-dev.sh
