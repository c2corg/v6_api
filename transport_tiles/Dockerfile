FROM debian:trixie-slim

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
