FROM logstash:6.8.23
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
