FROM logstash:7.0.1
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
