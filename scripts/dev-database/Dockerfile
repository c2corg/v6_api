# Lightweight anonymized dev database: PostgreSQL 18 + PostGIS, restored at the first start.
#   docker build --build-arg DUMP=c2corg-dev.dump -t c2corg-dev-db .
FROM postgis/postgis:18-3.6

ARG DUMP=c2corg-dev.dump
COPY ${DUMP} /docker-entrypoint-initdb.d/c2corg-dev.dump
COPY restore-dev.sh /docker-entrypoint-initdb.d/20-restore-dev.sh
