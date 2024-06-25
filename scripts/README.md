# ElasticSearch Upgrade from v6.8 to V7.22 for docker env. like dev one.

The docker-compose file has been updated in order to facilitate and automotive plugins installation and prepare the environment for migration.
The ElasticSearch 6.8 is still build and run but would not be the main ES for the service. It could be decommissioned after migration. 
docker-compose file contains as well :

- api building with integration of the requirements.txt for python pip installation (component updates)
- ES 6.8 listening on port 9201 instead of 9200 : > elasticsearch68
- redis no change
- postgresql no change
- ES 7.22 listening on port 9200 and 9300 (elasticsearch7.Dockerfile) > elasticsearch
- Logstash 7.22 for data migration purpose. (logstash7.Dockerfile) 

## migration steps

 1. **build the environment :**  ` docker-compose build `
 2. **Launch the environment :** ` docker-compose up -d `
 3. **Create the index and its mapping :** `./scripts/esUpdateMappings67.sh` 
 4. **Data Migration :** `docker-compose start logstash7` It will stop by itself when migration would be achieved
 5. **postgresql shema up to date:** `docker-compose exec api .build/venv/bin/alembic upgrade head`

## post migration

if all the process has been passed without issues. you can comment or remove in the docker-compose.yml services :
- logstash
- elasticsearch68

# ElasticSearch Upgrade from v5.6 to V6.8 for docker env. like dev one.

The docker-compose file has been updated in order to facilitate and automotive plugins installation and prepare the environment for migration.
The ElasticSearch 5.6 is still build and run but would not be the main ES for the service. It could be decommissioned after migration. 
docker-compose file contains as well :

- api building with integration of the requirements.txt for python pip installation (component updates)
- ES 5.6 listening on port 9201 instead of 9200 : > elasticsearch26
- redis no change
- postgresql no change
- ES 6.8 listening on port 9200 and 9300 (elasticsearch6.Dockerfile) > elasticsearch
- Logstash 6.8 for data migration purpose. (logstash6.Dockerfile) 

## migration steps

 1. **build the environment :**  ` docker-compose build `
 2. **Launch the environment :** ` docker-compose up -d `
 3. **Create the index and its mapping :** `./scripts/esUpdateMappings56.sh` 
 4. **Data Migration :** `docker-compose start logstash6` It will stop by itself when migration would be achieved
 5. **postgresql shema up to date:** `docker-compose exec api .build/venv/bin/alembic upgrade head`

## post migration

if all the process has been passed without issues. you can comment or remove in the docker-compose.yml services :
- logstash
- elasticsearch56

# ElasticSearch Upgrade from v2.6 to V5.6 for docker env. like dev one.

The docker-compose file has been updated in order to facilitate and automotive plugins installation and prepare the environment for migration.
The ElasticSearch 2.6 is still build and run but would not be the main ES for the service. It could be decommissioned after migration. 
docker-compose file contains as well :

- api building with integration of the requirements.txt for python pip installation (component updates)
- legacy ES 2.6 listening on port 9201 instead of 9200 : > elasticsearch26
- redis no change
- postgresql no change
- ES 5.6 listening on port 9200 and 9300 (elasticsearch5.Dockerfile) > elasticsearch
- Logstash 5.6 for data migration purpose. (logstash5.Dockerfile) 

## migration steps

 1. **build the environment :**  ` docker-compose build `
 2. **Launch the environment :** ` docker-compose up -d `
 3. **Create the index and its mapping :** `./scripts/esUpdateMappings25.sh` 
 4. **Data Migration :** `docker-compose run logstash5 /usr/share/logstash/bin/logstash -f /root/logstash.conf`
 5. **postgresql shema up to date:** `docker-compose exec api .build/venv/bin/alembic upgrade head`

## post migration

if all the process has been passed without issues. you can comment or remove in the docker-compose.yml services :
- logstash
- elasticsearch26

# ElasticSearch 2.6 update for search improvement

Script has to be execute one time in order to be relevant with the code update. 

## Script has to be execute from the host

### script requirement : 
- it requires curl from the execution machine
- it will update elasticsearch on localhost:9200, if elasticsearch is on other server, please update script changing localhost by the correct ES url.
- an elasticsearch plugin has to be install, in case of elasticsearch cluster - the plugin has to be install on each node


## To install manually the the plugin analysis-icu from elasticsearch server :

```
./bin/plugin install analysis-icu analysis-icu
```

The installation process is :
- Install the plugin, 
- restart ElasticSearch instance, 
- update analyser (_settings)
- update document mapping (_mappings /espon)
- start a full indexation.

## Automatic update via shell script from the host server

```
cd scripts/
./esUpdateMapSettings.sh
```


