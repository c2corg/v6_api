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
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_a"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_b"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_c"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_i"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_m"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_o"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_r"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_u"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_w"
curl -u elastic:elastic2024 -X DELETE "http://localhost:9200/c2corg_x"

#change cluster definition des shards
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/cluster.json http://localhost:9200/_template/index_defaults

#créer les index
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_a
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_b
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_c
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_i
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_m
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_o
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_r
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_u
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_w
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" http://localhost:9200/c2corg_x
sleep 2

#2. closing the index to upgrade settings
echo -e '\n closing index'
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_a/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_b/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_c/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_i/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_m/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_o/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_r/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_u/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_w/_close
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_x/_close
sleep 2
#3. Updating analyser settings
echo -e  '\n updating Settings'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_a/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_b/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_c/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_i/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_m/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_o/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_r/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_u/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_w/_settings
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/settings.json http://localhost:9200/c2corg_x/_settings
sleep 2
#4. restarting the index
echo -e  '\n restarting index'
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_a/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_b/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_c/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_i/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_m/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_o/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_r/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_u/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_w/_open
curl -u elastic:elastic2024 -X POST -H "Content-Type: application/json" http://localhost:9200/c2corg_x/_open
sleep 2
#5. Docs Mappings update
echo 'updating doc type mappings'
echo 'doc type : a'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/a.json http://localhost:9200/c2corg_a/_mapping
echo -e '\n doc type : b'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/b.json http://localhost:9200/c2corg_b/_mapping
echo -e '\n doc type : c'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/c.json http://localhost:9200/c2corg_c/_mapping
echo -e  '\n doc type : i'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/i.json http://localhost:9200/c2corg_i/_mapping
echo -e  '\n doc type : m'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/m.json http://localhost:9200/c2corg_m/_mapping
echo -e  '\n doc type : o'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/o.json http://localhost:9200/c2corg_o/_mapping
echo -e  '\n doc type : r'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/r.json http://localhost:9200/c2corg_r/_mapping
echo -e  '\n doc type : u'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/u.json http://localhost:9200/c2corg_u/_mapping
echo -e  '\n doc type : w'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/w.json http://localhost:9200/c2corg_w/_mapping
echo -e  '\n doc type : x'
curl -u elastic:elastic2024 -X PUT -H "Content-Type: application/json" -d @./scripts/esjson6-7/x.json http://localhost:9200/c2corg_x/_mapping
sleep 2
