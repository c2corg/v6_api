FROM logstash:7.0.0
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
