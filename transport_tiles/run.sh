#!/bin/sh
# Builds transport.pmtiles (public transport lines and stops from OpenStreetMap).
#
# One region at a time: the extract is deleted as soon as its lines and stops
# are written, so the disk never holds more than one extract. Sized for a
# 1 CPU / 1 GB / 10 GB machine (osmium-tool is not used: its tags-filter keeps
# an id bitmap that outgrows 1 GB on a regional extract).
#
#   REGIONS    space separated region ids from regions.json (default: all)
#   WORK_DIR   scratch directory (default /work)
#   OUT_DIR    where transport.pmtiles is written (default /out)
#   DATABASE_URL  read-only connection to the camptocamp database: the stop areas
#                 (guidebook.stopareas) are merged into the stops (merge_stopareas.py)
#   UPLOAD     set to 1 to push the result to S3 (see upload.py)
set -eu

WORK_DIR="${WORK_DIR:-/work}"
OUT_DIR="${OUT_DIR:-/out}"
REGIONS="${REGIONS:-$(jq -r '.[].id' regions.json | tr '\n' ' ')}"

mkdir -p "$WORK_DIR" "$OUT_DIR"
: > "$WORK_DIR/lines.geojsonl"
: > "$WORK_DIR/stops.geojsonl"

for region in $REGIONS; do
    url=$(jq -r --arg id "$region" '.[] | select(.id == $id) | .url' regions.json)
    [ -n "$url" ] || { echo "unknown region: $region" >&2; exit 1; }

    echo "== $region"
    if [ ! -s "$WORK_DIR/$region.osm.pbf" ]; then
        curl -fL --retry 3 -o "$WORK_DIR/$region.osm.pbf" "$url"
    fi

    python3 build_lines.py "$WORK_DIR/$region.osm.pbf" \
        "$WORK_DIR/lines.geojsonl" "$WORK_DIR/stops.geojsonl"
    [ -n "${KEEP_EXTRACTS:-}" ] || rm -f "$WORK_DIR/$region.osm.pbf"
done

echo "== borders"
python3 reconcile.py "$WORK_DIR/lines.geojsonl" "$WORK_DIR/stops.geojsonl"

if [ -n "${DATABASE_URL:-}" ]; then
    echo "== stop areas"
    python3 merge_stopareas.py "$WORK_DIR/stops.geojsonl"
fi

echo "== tiles"
tippecanoe --force --quiet -o "$OUT_DIR/transport.pmtiles" \
    -Z5 -z14 \
    --drop-densest-as-needed \
    --use-attribute-for-id=fid \
    --temporary-directory="$WORK_DIR" \
    -L lines:"$WORK_DIR/lines.geojsonl" \
    -L stops:"$WORK_DIR/stops.geojsonl"

ls -l "$OUT_DIR/transport.pmtiles"

if [ "${UPLOAD:-}" = "1" ]; then
    python3 upload.py "$OUT_DIR/transport.pmtiles"
fi
