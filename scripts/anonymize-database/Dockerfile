FROM c2corg/c2corg_pgsql:9.6.1-postgis2.3

COPY restore-dump.sh /docker-entrypoint-initdb.d/ZZZ-03-restore-dump.sh
COPY anonymize-data.sql /docker-entrypoint-initdb.d/ZZZ-04-anonymize-data.sql
COPY create-anonymous-dump.sh /docker-entrypoint-initdb.d/ZZZ-05-create-anonymous-dump.sh
