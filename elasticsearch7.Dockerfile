FROM elasticsearch:7.17.22
RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install analysis-icu
