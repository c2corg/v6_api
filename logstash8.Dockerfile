FROM logstash:8.14.1
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
