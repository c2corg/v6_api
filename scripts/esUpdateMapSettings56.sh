#!/bin/bash
#change localhost to the correct url if elasticsearch is not hosted on your computer, or in docker
#operate the plugin installation from the server side manually if not dockerized.
#installation du plugin es et reboot
#Install elastic plugin analysis-icu
#echo 'Installing es plugin to elasticsearch docker'
#docker-compose exec -it elasticsearch bin/plugin install analysis-icu
#echo 'Installing done - restarting es docker'
#docker-compose restart elasticsearch
#sleep 10 #in sec to let the docker restart

#efface tous les indices présents
curl -X DELETE "http://192.168.1.120:9203/c2corg_*"

#change cluster definition des shards
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/cluster.json http://192.168.1.120:9203/_template/index_defaults

#créer les index
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_a
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_b
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_c
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_i
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_m
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_o
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_r
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_u
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_w
curl -X PUT -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_x
sleep 2

#2. closing the index to upgrade settings
echo -e '\n closing index'
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_a/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_b/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_c/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_i/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_m/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_o/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_r/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_u/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_w/_close
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_x/_close
sleep 2
#3. Updating analyser settings
echo -e  '\n updating Settings'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_a/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_b/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_c/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_i/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_m/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_o/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_r/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_u/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_w/_settings
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/settings.json http://192.168.1.120:9203/c2corg_x/_settings
sleep 2
#4. restarting the index
echo -e  '\n restarting index'
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_a/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_b/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_c/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_i/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_m/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_o/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_r/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_u/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_w/_open
curl -X POST -H "Content-Type: application/json" http://192.168.1.120:9203/c2corg_x/_open
sleep 2
#5. Docs Mappings update
echo 'updating doc type mappings'
echo 'doc type : a'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/a.json http://192.168.1.120:9203/c2corg_a/_mapping/_doc
echo -e '\n doc type : b'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/b.json http://192.168.1.120:9203/c2corg_b/_mapping/_doc
echo -e '\n doc type : c'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/c.json http://192.168.1.120:9203/c2corg_c/_mapping/_doc
echo -e  '\n doc type : i'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/i.json http://192.168.1.120:9203/c2corg_i/_mapping/_doc
echo -e  '\n doc type : m'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/m.json http://192.168.1.120:9203/c2corg_m/_mapping/_doc
echo -e  '\n doc type : o'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/o.json http://192.168.1.120:9203/c2corg_o/_mapping/_doc
echo -e  '\n doc type : r'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/r.json http://192.168.1.120:9203/c2corg_r/_mapping/_doc
echo -e  '\n doc type : u'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/u.json http://192.168.1.120:9203/c2corg_u/_mapping/_doc
echo -e  '\n doc type : w'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/w.json http://192.168.1.120:9203/c2corg_w/_mapping/_doc
echo -e  '\n doc type : x'
curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/x.json http://192.168.1.120:9203/c2corg_x/_mapping/_doc
sleep 2
