FROM docker.io/debian:jessie

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL en_US.UTF-8

RUN set -x \
 && apt-get update \
 && apt-get -y upgrade \
 && apt-get -y --no-install-recommends install \
    python3 \
    python3-chardet \
    python3-colorama \
    python3-html5lib \
    python3-pkg-resources \
    python3-requests \
    python3-six \
    python3-urllib3 \
    libgeos-c1 \
    libpq5 \
    libffi6 \
    make \
    vim \
    sudo \
    python3-dev \
    python3-pip \
    libgeos-dev \
    libffi-dev \
    libpq-dev \
    virtualenv \
    gcc \
    git \
    locales \
 && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
 && locale-gen en_US.UTF-8 \
 && dpkg-reconfigure locales \
 && /usr/sbin/update-locale LANG=en_US.UTF-8

COPY ./ /var/www/

WORKDIR /var/www/

RUN set -x \
 && make -f config/docker-dev install \
 && py3compile -f -X '^.*gevent/_util_py2.py$' -X '^.*attr/_next_gen.py$' .build/venv/

ENV version="{version}" \
    PATH=/var/www/.build/venv/bin/:$PATH

COPY /docker-entrypoint.sh /
COPY /docker-entrypoint.d/* /docker-entrypoint.d/
ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 8080
CMD ["gunicorn", "--paste", "production.ini", "-u", "www-data", "-g", "www-data", "-b", ":8080"]