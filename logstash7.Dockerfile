FROM logstash:7.17.22
RUN /usr/share/logstash/bin/logstash-plugin install logstash-filter-prune
