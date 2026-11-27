FROM debian:trixie-slim

# the packages of the Debian release, with its security updates: a pinned
# version leaves the archive at the next update and breaks the build (as in
# docker/Dockerfile of the API)
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl jq tippecanoe \
        python3 python3-pyosmium python3-numpy python3-shapely python3-boto3 python3-psycopg2 python3-pytest \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY regions.json build_lines.py merge_stopareas.py reconcile.py upload.py run.sh pytest.ini ./
COPY tests ./tests
RUN chmod +x run.sh

ENV WORK_DIR=/work OUT_DIR=/out
CMD ["./run.sh"]
