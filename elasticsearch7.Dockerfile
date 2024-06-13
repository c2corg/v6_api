FROM elasticsearch:7.17.21
RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install analysis-icu
