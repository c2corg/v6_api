#!/bin/bash
# shellcheck disable=SC2001
# Fetches public transport stop areas from Navitia and populates the database.
# Runs from the HOST (outside containers), using podman-compose/docker-compose to reach psql.
#
# Usage: ./scripts/get_public_transports.sh [france|isere|rhone]
# Default region: france
#
# Required environment variables (set before calling this script):
#   NAVITIA_API_KEY                    Navitia API key
#   MAX_DISTANCE_WAYPOINT_TO_STOPAREA  Max distance in meters between waypoint and stop area
#   WALKING_SPEED                      Walking speed in m/s
#   MAX_STOP_AREA_FOR_1_WAYPOINT       Max number of stop areas per waypoint
#
# Optional environment variables:
#   PROJECT_NAME   Compose project name (default: "")
#   API_PORT       Local API port (default: 6543)
#   CCOMPOSE       Compose command (default: "podman-compose")
#   PODMAN_ENV     If set, script changes to the project root before running
#   PGUSER         PostgreSQL user (default: postgres)
#   PGDATABASE     PostgreSQL database (default: c2corg)

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

log "=== Script started (region: $REGION / area: $AREA_ID) ==="

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

# ============================================================
# CONFIGURATION
# ============================================================
SERVICE_NAME="postgresql"
DB_USER=${PGUSER:-postgres}
DB_NAME=${PGDATABASE:-c2corg}

PROJECT_NAME=${PROJECT_NAME:-""}
API_PORT=${API_PORT:-6543}
CCOMPOSE=${CCOMPOSE:-"podman-compose"}
STANDALONE=${PODMAN_ENV:-""}

if [[ -n "$STANDALONE" ]]; then
    SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    cd "$SCRIPTPATH"/../../.. || exit
fi

DURATION=$(echo "scale=0; $MAX_DISTANCE_WAYPOINT_TO_STOPAREA / $WALKING_SPEED" | bc)
MAX_STOP_AREA_FETCHED=$((MAX_STOP_AREA_FOR_1_WAYPOINT * 3))

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
for cmd in curl jq bc awk sed wc "$CCOMPOSE"; do
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
log "Checking database connection..."
if ! $CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -c "SELECT 1;" &>/dev/null; then
    log_err "Cannot connect to database. Check that the $SERVICE_NAME container is running."
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
    lon_lat=$($CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
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

    # --- Filter by transport diversity ---
    > /tmp/selected_stops.txt
    > /tmp/known_transports.txt
    selected_count=0

    for ((i=1; i<=stop_area_count && selected_count<MAX_STOP_AREA_FOR_1_WAYPOINT; i++)); do
        stop_id=$(sed "${i}q;d" /tmp/stop_ids.txt)

        stop_info=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/places/$stop_id")
        ((NAVITIA_REQUEST_COUNT++))

        echo "$stop_info" | jq -r '.places[0].stop_area.lines[] | .commercial_mode.name + " " + .code' \
            > /tmp/current_stop_transports.txt 2>/dev/null

        new_transport_found=false
        transport_count=$(wc -l < /tmp/current_stop_transports.txt)

        for ((t=1; t<=transport_count; t++)); do
            transport=$(sed "${t}q;d" /tmp/current_stop_transports.txt)
            if ! grep -Fxq "$transport" /tmp/known_transports.txt; then
                new_transport_found=true
                echo "$transport" >> /tmp/known_transports.txt
            fi
        done

        if [ "$new_transport_found" = true ]; then
            echo "$i" >> /tmp/selected_stops.txt
            ((selected_count++))
        fi
    done

    log "Waypoint $WAYPOINT_ID: selected $selected_count/$stop_area_count stop areas."

    # --- Process selected stops ---
    selected_stops_count=$(wc -l < /tmp/selected_stops.txt)
    for ((s=1; s<=selected_stops_count; s++)); do
        stop_index=$(sed "${s}q;d" /tmp/selected_stops.txt)
        stop_name=$(sed "${stop_index}q;d" /tmp/stop_names.txt)
        stop_id=$(sed "${stop_index}q;d" /tmp/stop_ids.txt)
        lat_stop=$(sed "${stop_index}q;d" /tmp/lat.txt)
        lon_stop=$(sed "${stop_index}q;d" /tmp/lon.txt)

        # Get walking travel time
        journey_response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" \
            "https://api.navitia.io/v1/journeys?to=$lon%3B$lat&walking_speed=$WALKING_SPEED&max_walking_direct_path_duration=$DURATION&direct_path_mode%5B%5D=walking&from=$stop_id&direct_path=only_with_alternatives")
        ((NAVITIA_REQUEST_COUNT++))

        has_error=$(echo "$journey_response" | jq -r 'has("error")' 2>/dev/null)
        if [[ "$has_error" == "true" ]]; then
            navitia_err=$(echo "$journey_response" | jq -r '.error.message // "unknown"' 2>/dev/null)
            log "Waypoint $WAYPOINT_ID / stop $stop_id: journey error ($navitia_err), skipping."
            continue
        fi

        walk_duration=$(echo "$journey_response" | jq -r '.journeys[0].duration // 0')
        distance_km=$(awk "BEGIN {printf \"%.2f\", ($walk_duration * $WALKING_SPEED) / 1000}")

        if [[ -n "${INSERTED_STOP_AREAS[$stop_id]+x}" ]]; then
            # Already inserted in this run: reference via navitia_id subquery
            echo "INSERT INTO guidebook.waypoints_stopareas (stoparea_id, waypoint_id, distance)
SELECT stoparea_id, $WAYPOINT_ID, $distance_km
FROM guidebook.stopareas WHERE navitia_id = '$stop_id';" >> "$SQL_FILE"
        else
            # New stop area: fetch full details and emit insert block
            stop_info=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/places/$stop_id")
            ((NAVITIA_REQUEST_COUNT++))

            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].name'                  > /tmp/lines.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].code'                  > /tmp/code.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].network.name'          > /tmp/network.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].commercial_mode.name'  > /tmp/mode.txt

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
    done

    rm -f /tmp/stop_names.txt /tmp/stop_ids.txt /tmp/lat.txt /tmp/lon.txt \
          /tmp/selected_stops.txt /tmp/known_transports.txt /tmp/current_stop_transports.txt
done

echo "COMMIT;" >> "$SQL_FILE"

log "Loop complete: $nb_waypoints waypoints processed. Total Navitia requests: $NAVITIA_REQUEST_COUNT. Errors: $ERROR_COUNT."
log "SQL file size: $(wc -l < "$SQL_FILE") lines."

# ============================================================
# EXECUTE SQL (atomic: truncate + all inserts in one transaction)
# ============================================================
log "Executing SQL file (this includes TRUNCATE + all inserts)..."
if $CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME < "$SQL_FILE"; then
    log "SQL executed successfully. Done."
else
    log_err "SQL execution FAILED. The database has NOT been modified. SQL file kept at: $SQL_FILE"
    exit 1
fi

log "=== Script completed ==="
