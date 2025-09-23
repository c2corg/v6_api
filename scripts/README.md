# ElasticSearch 2.4 update for search improvement

Script has to be execute one time in order to be relevant with the code update. 

## Script has to be execute from the host

### script requirement : 
- it requires curl from the execution machine

- it will update elasticsearch on localhost:9200, if elasticsearch is on other server, please update script changing localhost by the correct ES url.
- an elasticsearch plugin has to be install, in case of elasticsearch cluster - the plugin has to be install on each node

 
To install manually the the plugin analysis-icu from elasticsearch server :

```
./bin/plugin install analysis-icu analysis-icu
```


The installation process is :
- Install the plugin, 
- restart ElasticSearch instance, 
- update analyser (_settings)
- update document mapping (_mappings /espon)
- start a full indexation.

To launch the script from the host side :
```
cd scripts/
./esUpdateMapSettings.sh
```


