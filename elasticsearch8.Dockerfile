FROM elasticsearch:8.14.1
RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install analysis-icu
