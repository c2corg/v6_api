FROM docker.io/debian:buster-slim

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL en_US.UTF-8

RUN set -x \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get -y --no-install-recommends install locales \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && dpkg-reconfigure locales \
    && /usr/sbin/update-locale LANG=en_US.UTF-8

COPY ./ /var/www/

WORKDIR /var/www/

RUN set -x \
    && apt-get -y --no-install-recommends install \
    python3 \
    python3-chardet \
    python3-colorama \
    python3-html5lib \
    python3-pkg-resources \
    python3-requests \
    python3-six \
    python3-urllib3 \
    libgeos-c1v5 \
    libpq5 \
    libffi6 \
    make \
    python3-dev \
    python3-pip \
    libgeos-dev \
    libffi-dev \
    libpq-dev \
    virtualenv \
    gcc \
    git

RUN set -x \
 && make -f config/docker-dev install \
 && make -f config/docker-dev .build/dev-requirements.timestamp \
 && py3compile -f .build/venv/ \
 && rm -fr .cache \
 && apt-get -y purge \
 && apt-get -y --purge autoremove \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV version='' \
    PATH=/var/www/.build/venv/bin/:$PATH

RUN make -f config/docker-dev template
