FROM logstash:7.17.21
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
