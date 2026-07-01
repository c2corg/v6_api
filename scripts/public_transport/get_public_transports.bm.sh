#!/bin/bash
# shellcheck disable=SC2001
# Fetches public transport stop areas from Navitia and populates the database.
# "bare metal" variant: uses psql directly (no container/compose).
# Intended to run FROM WITHIN a container or on a machine with direct DB access.
#
# Usage: ./scripts/get_public_transports.bm.sh [france|isere|rhone]
# Default region: france
#
# Required environment variables (set before calling this script):
#   NAVITIA_API_KEY                    Navitia API key
#   MAX_DISTANCE_WAYPOINT_TO_STOPAREA  Max distance in meters between waypoint and stop area
#   WALKING_SPEED                      Walking speed in m/s
#   MAX_STOP_AREA_FOR_1_WAYPOINT       Max number of stop areas per waypoint
#
# Optional environment variables:
#   API_PORT    Local API port (default: 6543)
#   PGUSER      PostgreSQL user (default: postgres)
#   PGDATABASE  PostgreSQL database (default: c2corg)
#   PGHOST      PostgreSQL host (default: localhost)
#   PGPORT      PostgreSQL port (default: 5432)
#   PGPASSWORD  PostgreSQL password (forwarded to psql natively)
#   PGSSLCERT   PostgreSQL SSL certificate (forwarded to psql natively)

set -uo pipefail

# ============================================================
# REGION SELECTION
# ============================================================
REGION="${1:-france}"
case "$REGION" in
    france) AREA_ID=14274 ;;
    isere)  AREA_ID=14328 ;;
    rhone)  AREA_ID=14299 ;;
    *)
        echo "ERROR: Unknown region '$REGION'. Valid values: france, isere, rhone" >&2
        exit 1
        ;;
esac

# ============================================================
# LOGGING
# ============================================================
LOG_FILE="log-navitia.txt"
> "$LOG_FILE"

log()     { echo "[$(date +"%Y-%m-%d %H:%M:%S")] $*" | tee -a "$LOG_FILE"; }
log_err() { echo "[$(date +"%Y-%m-%d %H:%M:%S")] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

log "=== Script started (bare metal, region: $REGION / area: $AREA_ID) ==="

# ============================================================
# CHECK REQUIRED ENV VARS
# ============================================================
log "Checking required environment variables..."
missing_vars=0
for var in NAVITIA_API_KEY MAX_DISTANCE_WAYPOINT_TO_STOPAREA WALKING_SPEED MAX_STOP_AREA_FOR_1_WAYPOINT; do
    if [[ -z "${!var:-}" ]]; then
        log_err "Required variable $var is not set."
        missing_vars=1
    fi
done
[[ "$missing_vars" -eq 1 ]] && exit 1
log "All required environment variables are set."
log "MAX_DISTANCE_WAYPOINT_TO_STOPAREA: $MAX_DISTANCE_WAYPOINT_TO_STOPAREA"
log "WALKING_SPEED: $WALKING_SPEED"
log "MAX_STOP_AREA_FOR_1_WAYPOINT: $MAX_STOP_AREA_FOR_1_WAYPOINT"

# ============================================================
# CONFIGURATION
# ============================================================
# Standard PostgreSQL env vars are read natively by psql.
# Defaults applied only if not already set in the environment.
export PGUSER=${PGUSER:-postgres}
export PGDATABASE=${PGDATABASE:-c2corg}
export PGHOST=${PGHOST:-localhost}
export PGPORT=${PGPORT:-5432}
# PGPASSWORD and PGSSLCERT are forwarded as-is if set in the environment.

psql_cmd() {
    psql "$@"
}

API_PORT=${API_PORT:-6543}
DURATION=$(echo "scale=0; $MAX_DISTANCE_WAYPOINT_TO_STOPAREA / $WALKING_SPEED" | bc)
MAX_DISTANCE_KM=$(awk "BEGIN {printf \"%.6f\", $MAX_DISTANCE_WAYPOINT_TO_STOPAREA / 1000}")
# Augmenter le nombre d'arrêts récupérés pour avoir plus de choix
MAX_STOP_AREA_FETCHED=$((MAX_STOP_AREA_FOR_1_WAYPOINT * 3)) # Récupérer 6 fois plus d'arrêts

BASE_API_URL="http://localhost:${API_PORT}/waypoints?wtyp=access&a=${AREA_ID}&limit=100"
OUTPUT_FILE="/tmp/waypoints_ids.txt"
SQL_FILE="/tmp/sql_commands.sql"
NAVITIA_REQUEST_COUNT=0
ERROR_COUNT=0

# ============================================================
# CHECK REQUIRED COMMANDS
# ============================================================
log "Checking required commands..."
missing_cmds=0
for cmd in curl jq bc awk sed wc psql; do
    if ! command -v "$cmd" &>/dev/null; then
        log_err "Required command not found: $cmd"
        missing_cmds=1
    fi
done
[[ "$missing_cmds" -eq 1 ]] && exit 1
log "All required commands are available."

# ============================================================
# PRE-FLIGHT: CHECK DB CONNECTION
# ============================================================
log "Checking database connection (${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE})..."
if ! psql_cmd -c "SELECT 1;" &>/dev/null; then
    log_err "Cannot connect to database. Check PGHOST/PGUSER/PGPASSWORD/PGDATABASE/PGPORT/PGSSLCERT."
    exit 1
fi
log "Database connection OK."

# ============================================================
# PRE-FLIGHT: CHECK NAVITIA API
# ============================================================
log "Checking Navitia API..."
navitia_http=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/")
if [[ "$navitia_http" != "200" ]]; then
    log_err "Navitia API returned HTTP $navitia_http. Check NAVITIA_API_KEY."
    exit 1
fi
log "Navitia API OK (HTTP 200)."

# ============================================================
# PRE-FLIGHT: CHECK LOCAL WAYPOINTS API
# ============================================================
log "Checking local waypoints API on port $API_PORT..."
api_http=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${API_PORT}/waypoints?wtyp=access&a=${AREA_ID}&limit=1")
if [[ "$api_http" != "200" ]]; then
    log_err "Waypoints API returned HTTP $api_http. Check the API server is running on port $API_PORT."
    exit 1
fi
log "Waypoints API OK (HTTP 200)."

# ============================================================
# FETCH ALL WAYPOINT IDS (PAGINATED)
# ============================================================
log "Fetching waypoint IDs for region '$REGION'..."
> "$OUTPUT_FILE"

OFFSET=0
LIMIT=100

while true; do
    API_URL="${BASE_API_URL}&offset=${OFFSET}"
    response=$(curl -s "$API_URL")
    WAYPOINTS_IDS=$(echo "$response" | jq -r '.documents[]? | .document_id' 2>/dev/null)

    if [[ -z "$WAYPOINTS_IDS" ]]; then
        log "No more waypoints at offset $OFFSET. Stopping pagination."
        break
    fi

    nb_current=$(echo "$WAYPOINTS_IDS" | grep -c '[0-9]' || true)
    echo "$WAYPOINTS_IDS" >> "$OUTPUT_FILE"
    log "Fetched $nb_current waypoints at offset $OFFSET."
    OFFSET=$((OFFSET + LIMIT))
done

nb_waypoints=$(grep -c '[0-9]' "$OUTPUT_FILE" 2>/dev/null || echo 0)
log "Total waypoints fetched: $nb_waypoints"

if [[ "$nb_waypoints" -eq 0 ]]; then
    log_err "No waypoints found. Exiting."
    exit 1
fi

# ============================================================
# INITIALIZE SQL FILE
# TRUNCATE is placed here so the entire operation (truncate + inserts)
# runs atomically at the end, avoiding an empty DB during the long loop.
# ============================================================
log "Initializing SQL file..."
cat > "$SQL_FILE" << 'ENDSQL'
BEGIN;
TRUNCATE TABLE guidebook.waypoints_stopareas RESTART IDENTITY;
TRUNCATE TABLE guidebook.stopareas RESTART IDENTITY;
ENDSQL

# Track stop areas inserted in this run to avoid querying the (not-yet-truncated) DB.
declare -A INSERTED_STOP_AREAS

# ============================================================
# MAIN LOOP
# ============================================================
for ((k=1; k<=nb_waypoints; k++)); do
    # Log progress every 10 waypoints
    if (( k % 10 == 0 )) || (( k == 1 )); then
        log "Progress: $k/$nb_waypoints — Navitia requests: $NAVITIA_REQUEST_COUNT — Errors: $ERROR_COUNT"
    fi

    WAYPOINT_ID=$(sed "${k}q;d" "$OUTPUT_FILE")

    if [[ -z "$WAYPOINT_ID" ]]; then
        log_err "Empty WAYPOINT_ID at line $k, skipping."
        ((ERROR_COUNT++))
        continue
    fi

    # --- Get waypoint coordinates ---
    lon_lat=$(psql_cmd -t -c "
        SELECT ST_X(ST_Transform(geom, 4326)) || ',' || ST_Y(ST_Transform(geom, 4326))
        FROM guidebook.documents_geometries
        WHERE document_id = $WAYPOINT_ID;
    " 2>/dev/null | tr -d ' \n\r')

    lon=$(echo "$lon_lat" | cut -d',' -f1)
    lat=$(echo "$lon_lat" | cut -d',' -f2)

    if [[ -z "$lon" || -z "$lat" || "$lon" == "null" || "$lat" == "null" ]]; then
        log "Waypoint $WAYPOINT_ID: no coordinates found, skipping."
        continue
    fi

    # --- Query Navitia for nearby stop areas ---
    response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" \
        "https://api.navitia.io/v1/coord/$lon%3B$lat/places_nearby?type%5B%5D=stop_area&count=$MAX_STOP_AREA_FETCHED&distance=$MAX_DISTANCE_WAYPOINT_TO_STOPAREA")
    ((NAVITIA_REQUEST_COUNT++))

    if [[ -z "$response" ]]; then
        log_err "Waypoint $WAYPOINT_ID: empty response from Navitia for coord $lon;$lat."
        ((ERROR_COUNT++))
        continue
    fi

    has_places=$(echo "$response" | jq 'has("places_nearby") and (.places_nearby | length > 0)' 2>/dev/null)

    if [[ "$has_places" != "true" ]]; then
        log "Waypoint $WAYPOINT_ID: no nearby stop areas."
        continue
    fi

    echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .name' > /tmp/stop_names.txt
    echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .id'   > /tmp/stop_ids.txt
    echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lat' > /tmp/lat.txt
    echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lon' > /tmp/lon.txt

    stop_area_count=$(wc -l < /tmp/stop_ids.txt)

    # --- Single-pass selection: transport diversity + walking validation + insert ---
    > /tmp/known_transports.txt
    selected_count=0

    # Process stops in order (already sorted by straight-line distance by Navitia)
    for ((i=1; i<=stop_area_count && selected_count<MAX_STOP_AREA_FOR_1_WAYPOINT; i++)); do
        stop_name=$(sed "${i}q;d" /tmp/stop_names.txt)
        stop_id=$(sed "${i}q;d" /tmp/stop_ids.txt)
        lat_stop=$(sed "${i}q;d" /tmp/lat.txt)
        lon_stop=$(sed "${i}q;d" /tmp/lon.txt)

        # Fetch stop details once and reuse them later if inserted.
        stop_info=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/places/$stop_id")
        ((NAVITIA_REQUEST_COUNT++))

        echo "$stop_info" | jq -r '.places[0].stop_area.lines[]? | .commercial_mode.name + " " + .code' \
            > /tmp/current_stop_transports.txt 2>/dev/null

        new_transport_found=false
        transport_count=$(wc -l < /tmp/current_stop_transports.txt)

        for ((t=1; t<=transport_count; t++)); do
            transport=$(sed "${t}q;d" /tmp/current_stop_transports.txt)
            if ! grep -Fxq "$transport" /tmp/known_transports.txt; then
                new_transport_found=true
                break
            fi
        done

        # No new transport contribution: skip without extra Navitia calls.
        if [ "$new_transport_found" != true ]; then
            continue
        fi

        # Get walking travel time
        journey_response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" \
            "https://api.navitia.io/v1/journeys?to=$lon%3B$lat&walking_speed=$WALKING_SPEED&max_duration_to_pt=$DURATION&direct_path_mode%5B%5D=walking&from=$stop_id&direct_path=only_with_alternatives")
        ((NAVITIA_REQUEST_COUNT++))

        has_error=$(echo "$journey_response" | jq -r 'has("error")' 2>/dev/null)
        if [[ "$has_error" == "true" ]]; then
            navitia_err=$(echo "$journey_response" | jq -r '.error.message // "unknown"' 2>/dev/null)
            log "Waypoint $WAYPOINT_ID / stop $stop_id: journey error ($navitia_err), skipping."
            continue
        fi

        has_journey=$(echo "$journey_response" | jq -r '.journeys | length > 0' 2>/dev/null)
        if [[ "$has_journey" != "true" ]]; then
            log "Waypoint $WAYPOINT_ID / stop $stop_id: no walking journey found, skipping."
            continue
        fi

        walk_duration=$(echo "$journey_response" | jq -r '.journeys[0].duration // 0')
        distance_km=$(awk "BEGIN {printf \"%.2f\", ($walk_duration * $WALKING_SPEED) / 1000}")

        over_distance_limit=$(awk "BEGIN {print (($distance_km > $MAX_DISTANCE_KM) ? 1 : 0)}")
        if [[ "$over_distance_limit" -eq 1 ]]; then
            log "Waypoint $WAYPOINT_ID / stop $stop_id: walking distance ${distance_km}km exceeds ${MAX_DISTANCE_KM}km, skipping."
            continue
        fi

        if [[ -n "${INSERTED_STOP_AREAS[$stop_id]+x}" ]]; then
            # Already inserted in this run: reference via navitia_id subquery
            echo "INSERT INTO guidebook.waypoints_stopareas (stoparea_id, waypoint_id, distance)
SELECT stoparea_id, $WAYPOINT_ID, $distance_km
FROM guidebook.stopareas WHERE navitia_id = '$stop_id';" >> "$SQL_FILE"
        else
            # New stop area: use cached stop details and emit insert block
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[]? | .name'                  > /tmp/lines.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[]? | .code'                  > /tmp/code.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[]? | .network.name'          > /tmp/network.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[]? | .commercial_mode.name'  > /tmp/mode.txt

            stop_count=$(wc -l < /tmp/lines.txt)

            if [[ "$stop_count" -eq 0 ]]; then
                log "Waypoint $WAYPOINT_ID / stop $stop_id: no lines found, skipping."
                rm -f /tmp/lines.txt /tmp/code.txt /tmp/network.txt /tmp/mode.txt
                continue
            fi

            for ((j=1; j<=stop_count; j++)); do
                line_full_name=$(sed "${j}q;d" /tmp/lines.txt)
                line_name=$(sed "${j}q;d" /tmp/code.txt)
                operator_name=$(sed "${j}q;d" /tmp/network.txt)
                mode=$(sed "${j}q;d" /tmp/mode.txt)

                # shellcheck disable=SC2001
                echo "DO \$\$
                DECLARE stoparea_doc_id integer;
                BEGIN
                    INSERT INTO guidebook.stopareas (navitia_id, stoparea_name, line, operator, geom)
                    VALUES ('$stop_id', '$(echo "$stop_name" | sed "s/'/''/g")', '$mode $line_name - $(echo "$line_full_name" | sed "s/'/''/g")', '$(echo "$operator_name" | sed "s/'/''/g")', ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857))
                    RETURNING stoparea_id INTO stoparea_doc_id;

                    INSERT INTO guidebook.waypoints_stopareas (stoparea_id, waypoint_id, distance)
                    VALUES (stoparea_doc_id, $WAYPOINT_ID, $distance_km);
                END \$\$;" >> "$SQL_FILE"
            done

            INSERTED_STOP_AREAS[$stop_id]="inserted"
            rm -f /tmp/lines.txt /tmp/code.txt /tmp/network.txt /tmp/mode.txt
        fi

        # Add transports only after the stop has been retained.
        for ((t=1; t<=transport_count; t++)); do
            transport=$(sed "${t}q;d" /tmp/current_stop_transports.txt)
            if ! grep -Fxq "$transport" /tmp/known_transports.txt; then
                echo "$transport" >> /tmp/known_transports.txt
            fi
        done

        ((selected_count++))
    done

    log "Waypoint $WAYPOINT_ID: selected $selected_count/$stop_area_count stop areas."

    rm -f /tmp/stop_names.txt /tmp/stop_ids.txt /tmp/lat.txt /tmp/lon.txt \
          /tmp/known_transports.txt /tmp/current_stop_transports.txt
done

echo "COMMIT;" >> "$SQL_FILE"

log "Loop complete: $nb_waypoints waypoints processed. Total Navitia requests: $NAVITIA_REQUEST_COUNT. Errors: $ERROR_COUNT."
log "SQL file size: $(wc -l < "$SQL_FILE") lines."

# ============================================================
# EXECUTE SQL (atomic: truncate + all inserts in one transaction)
# ============================================================
log "Executing SQL file (this includes TRUNCATE + all inserts)..."
if psql_cmd -q < "$SQL_FILE"; then
    log "SQL executed successfully. Done."
else
    log_err "SQL execution FAILED. The database has NOT been modified. SQL file kept at: $SQL_FILE"
    exit 1
fi

log "=== Script completed ==="
