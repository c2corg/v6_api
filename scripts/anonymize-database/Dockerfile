FROM c2corg/c2corg_pgsql:9.6.1-postgis2.3

ADD restore-dump.sh /docker-entrypoint-initdb.d/ZZZ-03-restore-dump.sh
ADD anonymize-data.sql /docker-entrypoint-initdb.d/ZZZ-04-anonymize-data.sql
ADD create-anonymous-dump.sh /docker-entrypoint-initdb.d/ZZZ-05-create-anonymous-dump.sh
