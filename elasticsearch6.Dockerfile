FROM elasticsearch:6.8.23
RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install analysis-icu
