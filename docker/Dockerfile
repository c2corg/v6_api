FROM docker.io/python:3.9-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=en_US.UTF-8

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

CMD ["gunicorn", "--paste", "production.ini", "-u", "www-data", "-g", "www-data", "-b", ":8080"]
