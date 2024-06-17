#!/bin/bash
#change localhost to the correct url if elasticsearch is not hosted on your computer, or in docker
#operate the plugin installation from the server side manually if not dockerized.
#installation du plugin es et reboot
#Install elastic plugin analysis-icu
echo 'Installing es plugin to elasticsearch docker'
docker-compose exec -it elasticsearch bin/plugin install analysis-icu
echo 'Installing done - restarting es docker'
docker-compose restart elasticsearch
sleep 10 #in sec to let the docker restart

#2. closing the index to upgrade settings
echo -e '\n closing index'
curl -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg/_close
sleep 2
#3. Updating analyser settings
echo -e  '\n updating Settings'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/settings.json http://localhost:9200/c2corg/_settings
sleep 2
#4. restarting the index
echo -e  '\n restarting index'
curl -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg/_open
sleep 2
#5. Docs Mappings update
echo 'updating doc type mappings'
echo 'doc type : a'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/a.json http://localhost:9200/c2corg/_mapping/a
echo -e '\n doc type : b'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/b.json http://localhost:9200/c2corg/_mapping/b
echo -e '\n doc type : c'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/c.json http://localhost:9200/c2corg/_mapping/c
echo -e  '\n doc type : i'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/i.json http://localhost:9200/c2corg/_mapping/i
echo -e  '\n doc type : m'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/m.json http://localhost:9200/c2corg/_mapping/m
echo -e  '\n doc type : o'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/o.json http://localhost:9200/c2corg/_mapping/o
echo -e  '\n doc type : r'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/r.json http://localhost:9200/c2corg/_mapping/r
echo -e  '\n doc type : u'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/u.json http://localhost:9200/c2corg/_mapping/u
echo -e  '\n doc type : w'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/w.json http://localhost:9200/c2corg/_mapping/w
echo -e  '\n doc type : x'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson/x.json http://localhost:9200/c2corg/_mapping/x
sleep 2
#6. RE-index the indice to apply mappings
echo -e  '\n Indexing with new parameters - should take sometimes - pls wait server acknowlegment'
curl -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg/_update_by_query?conflicts=proceed