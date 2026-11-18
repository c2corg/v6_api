#!/bin/sh
# Measures what vector tiles of the tracks cost the database. READ ONLY, but run it on the
# PREPROD (a copy of production on PostgreSQL 18 + PostGIS 3.6) or on a replica: not on the
# primary of production, and the PostgreSQL 9.6 of the old fleet has no ST_TileEnvelope.
#
#   PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=c2corg sh run.sh [output folder]
#
# 1. info.txt: the version, the sizes, the number of tracks, their points.
# 2. tiles.csv + plans/: the time of each tile of a few places and zooms, the first time
#    (cold) and the second (warm), its size and its features, and the EXPLAIN of the warm one.
# 3. load.txt: pgbench on random places by zoom, for 1, 4 and 8 clients: tiles per second,
#    median and 95th percentile of the time, and what the database read (blocks).
# Takes about 10 minutes. Stop it with Ctrl-C at any time: nothing is written to the database.
set -eu

dir=$(cd "$(dirname "$0")" && pwd)
out=${1:-track-tiles-benchmark-$(date +%Y%m%d-%H%M)}
mkdir -p "$out/plans"
# never longer than a minute, never a write
export PGOPTIONS='-c statement_timeout=60000 -c default_transaction_read_only=on'
PSQL='psql -X -q -v ON_ERROR_STOP=1'

echo "Output: $out"
$PSQL -f "$dir/info.sql" > "$out/info.txt"
cat "$out/info.txt"

tile_of() { # lon lat zoom -> "tx ty"
    $PSQL -At -F ' ' -c "SELECT floor((ST_X(p) + 20037508.3427892) / (40075016.6855784 / 2 ^ $3))::int,
        floor((20037508.3427892 - ST_Y(p)) / (40075016.6855784 / 2 ^ $3))::int
        FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3857) AS p) s"
}
sql_of() { # zoom tx ty -> the tile query
    sed -e "s/:zoom/$1/g" -e "s/:tx/$2/g" -e "s/:ty/$3/g" "$dir/tile.sql"
}
run_ms() { # runs EXPLAIN ANALYZE, prints the execution time in ms, keeps the plan in $1
    $PSQL -At -c "EXPLAIN (ANALYZE, BUFFERS, SUMMARY) $(sql_of "$2" "$3" "$4")" > "$1" 2>&1 || true
    sed -n 's/^Execution Time: \([0-9.]*\) ms.*/\1/p' "$1"
}

echo 'place,zoom,tx,ty,bytes,features,first_ms,warm_ms' > "$out/tiles.csv"
# name lon lat: the dense places (Mont-Blanc, Grenoble, Pyrenees) and a quiet one
for place in 'chamonix 6.87 45.92' 'vercors 5.6 45.05' 'pyrenees 0.0 42.8' 'paris 2.35 48.85'; do
    set -- $place
    for zoom in 7 9 11 13; do
        set -- $place
        xy=$(tile_of "$2" "$3" "$zoom")
        tx=${xy% *}
        ty=${xy#* }
        echo "$1 z$zoom $tx/$ty"
        first=$(run_ms "$out/plans/$1-$zoom-first.txt" "$zoom" "$tx" "$ty")
        warm=$(run_ms "$out/plans/$1-$zoom.txt" "$zoom" "$tx" "$ty")
        size=$($PSQL -At -F ',' -c "$(sql_of "$zoom" "$tx" "$ty")" 2> /dev/null || true)
        # an empty time is a tile that took more than the minute allowed
        echo "$1,$zoom,$tx,$ty,${size:-timeout,timeout},${first:-timeout},${warm:-timeout}" >> "$out/tiles.csv"
    done
done
cat "$out/tiles.csv"

cat "$dir/bench-head.sql" "$dir/tile.sql" > "$out/bench.sql"
: > "$out/load.txt"
for zoom in 9 11 13; do
    for clients in 1 4 8; do
        rm -f pgbench_log.*
        stat() { $PSQL -At -F ' ' -c "SELECT blks_read, blks_hit FROM pg_stat_database WHERE datname = current_database()"; }
        before=$(stat)
        pgbench -n -c "$clients" -j "$clients" -T 30 -D zoom=$zoom -D tx=0 -D ty=0 -l -f "$out/bench.sql" \
            > "$out/pgbench-$zoom-$clients.txt" 2>&1 || true
        after=$(stat)
        tps=$(sed -n 's/^tps = \([0-9.]*\).*/\1/p' "$out/pgbench-$zoom-$clients.txt" | head -1)
        # the log of the transactions: client, number, time in microseconds...
        times=$(cat pgbench_log.* 2>/dev/null | awk '{print $3}' | sort -n)
        n=$(echo "$times" | grep -c . || true)
        p50=$(echo "$times" | awk -v n="$n" 'NR==int(n*0.50)+1 {printf "%.0f", $1/1000}')
        p95=$(echo "$times" | awk -v n="$n" 'NR==int(n*0.95)+1 {printf "%.0f", $1/1000}')
        echo "zoom=$zoom clients=$clients tiles=$n tps=${tps:-?} p50_ms=${p50:-?} p95_ms=${p95:-?} blocks_read/hit before='$before' after='$after'" | tee -a "$out/load.txt"
        rm -f pgbench_log.*
    done
done
echo "Done: $out"
