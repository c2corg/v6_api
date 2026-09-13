FROM docker.io/python:3.9-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=en_US.UTF-8

# Debian 11 (bullseye) is old enough that deb.debian.org's bullseye-security
# pool has started drifting out of sync with its own package index (some
# package files 404 while still listed, and which ones varies from run to
# run). Pinning to a single snapshot.debian.org timestamp keeps the index
# and the pool consistent with each other.
RUN set -x \
    && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260731T213502Z bullseye main" \
       > /etc/apt/sources.list \
    && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20260731T213502Z bullseye-security main" \
       >> /etc/apt/sources.list \
    && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260731T213502Z bullseye-updates main" \
       >> /etc/apt/sources.list

RUN set -x \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get -y --no-install-recommends install locales \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && dpkg-reconfigure locales \
    && /usr/sbin/update-locale LANG=en_US.UTF-8

RUN set -x \
    && apt-get -y --no-install-recommends install \
    git \
    libffi7 \
    libgeos-c1v5 \
    libpq5

RUN set -x \
 && apt-get -y purge \
 && apt-get -y --purge autoremove \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip

ARG VERSION
ENV version=$VERSION

WORKDIR /var/www/

ADD project.tar .
RUN chown -R root:root /var/www \
 && pip install .

EXPOSE 8080
ENTRYPOINT ["./docker/scripts/entrypoint.sh"]

CMD ["gunicorn", "--paste", "production.ini", "-u", "www-data", "-g", "www-data", "-b", ":8080", "--timeout", "120"]
