# Elasticsearch index of the dev database, already filled (built by publish-es.sh).
# Elasticsearch 2.4 as in production, with the ICU analysis plugin the index settings need.
FROM docker.io/elasticsearch:2.4.6-alpine AS empty

RUN bin/plugin install --batch analysis-icu \
 # the image declares /usr/share/elasticsearch/data as a VOLUME: what is written there is not kept in an image
 && echo 'path.data: /usr/share/elasticsearch/baked' >> config/elasticsearch.yml \
 && mkdir baked && chown elasticsearch:elasticsearch baked

FROM empty
# copied out of the container which filled the index, once stopped
COPY --chown=elasticsearch:elasticsearch esdata /usr/share/elasticsearch/baked
