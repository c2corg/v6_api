#!/bin/bash
# shellcheck disable=SC2001

DURATION=$(echo "scale=0; $MAX_DISTANCE_WAYPOINT_TO_STOPAREA / $WALKING_SPEED" | bc)

API_PORT=${API_PORT:-6543} 

BASE_API_URL="http://localhost:${API_PORT}/waypoints?wtyp=access&a=14299&limit=100" 
OUTPUT_FILE="/tmp/waypoints_ids.txt"
LOG_FILE="log-navitia.txt"
NAVITIA_REQUEST_COUNT=0
SQL_FILE="/tmp/sql_commands.sql"

echo "Start time :" > "$LOG_FILE"
echo $(date +"%Y-%m-%d-%H-%M-%S") >> "$LOG_FILE"

# --- Pagination logic ---
OFFSET=0
LIMIT=100 # The default API limit
TOTAL_WAYPOINTS=0


> "$OUTPUT_FILE"

while true; do
    API_URL="${BASE_API_URL}&offset=${OFFSET}"
    echo "Fetching: $API_URL" >> "$LOG_FILE"
    WAYPOINTS_IDS=$(curl -s "$API_URL" | jq -r '.documents[] | .document_id' 2>/dev/null)
    
    nb_current_waypoints=$(echo "$WAYPOINTS_IDS" | wc -l)

    # If jq returned one line (no waypoint message), or if wc -l returned 0 ==> there is nothing left
    if [ "$nb_current_waypoints" -eq 1 ]; then
        echo "No more waypoints to fetch. Breaking loop." >> "$LOG_FILE"
        break
    fi

    echo "$WAYPOINTS_IDS" >> "$OUTPUT_FILE"
    
    TOTAL_WAYPOINTS=$((TOTAL_WAYPOINTS + nb_current_waypoints))
    OFFSET=$((OFFSET + LIMIT))

done

nb_waypoints=$(wc -l < "$OUTPUT_FILE")
echo "Total waypoints fetched: $nb_waypoints" >> "$LOG_FILE"
echo "Total waypoints fetched: $nb_waypoints"


# Initialize SQL file
> "$SQL_FILE"

psql -t -c "TRUNCATE TABLE guidebook.waypoints_stopareas RESTART IDENTITY;"
psql -t -c "TRUNCATE TABLE guidebook.stopareas RESTART IDENTITY;"




for ((k=1; k<=nb_waypoints; k++)); do
    # Log progress every 10 waypoints
    if (( k % 10 == 0 )) || (( k == 1 )); then
        echo "Progress: $k/$nb_waypoints waypoints processed. Navitia API requests: $NAVITIA_REQUEST_COUNT" >> $LOG_FILE
    fi

    WAYPOINT_ID=$(sed "${k}q;d" /tmp/waypoints_ids.txt)

    # Get waypoint coordinates from backend
    lon_lat=$(psql -t -c "
        SELECT ST_X(ST_Transform(geom, 4326)) || ',' || ST_Y(ST_Transform(geom, 4326)) 
        FROM guidebook.documents_geometries 
        WHERE document_id = $WAYPOINT_ID;
    " | tr -d ' ')

    # Extract longitude and latitude
    lon=$(echo "$lon_lat" | cut -d',' -f1)
    lat=$(echo "$lon_lat" | cut -d',' -f2)

    # Check that coordinates were retrieved successfully
    if [[ -z "$lon" || -z "$lat" || "$lon" == "null" || "$lat" == "null" ]]; then
        continue
    fi

    # Query Navitia to retrieve nearby stopareas
    response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/coord/$lon%3B$lat/places_nearby?type%5B%5D=stop_area&count=$MAX_STOP_AREA_FOR_1_WAYPOINT&distance=$MAX_DISTANCE_WAYPOINT_TO_STOPAREA")
    ((NAVITIA_REQUEST_COUNT++))

    has_places=$(echo "$response" | jq 'has("places_nearby") and (.places_nearby | length > 0)')

    if [[ "$has_places" == "true" ]]; then
        # Extract all stop names and IDs to temporary files
        echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .name' > /tmp/stop_names.txt
        echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .id' > /tmp/stop_ids.txt
        echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lat' > /tmp/lat.txt
        echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lon' > /tmp/lon.txt

        # Count the number of stops
        stop_area_count=$(wc -l < /tmp/stop_ids.txt)

        # Process stops in parallel
        for ((i=1; i<=stop_area_count; i++)); do
            stop_name=$(sed "${i}q;d" /tmp/stop_names.txt)
            stop_id=$(sed "${i}q;d" /tmp/stop_ids.txt)
            lat_stop=$(sed "${i}q;d" /tmp/lat.txt)
            lon_stop=$(sed "${i}q;d" /tmp/lon.txt)

            # Get walking travel time via Navitia
            journey_response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/journeys?to=$lon%3B$lat&walking_speed=$WALKING_SPEED&max_walking_direct_path_duration=$DURATION&direct_path_mode%5B%5D=walking&from=$stop_id&direct_path=only_with_alternatives")
            ((NAVITIA_REQUEST_COUNT++))

            # Check if Navitia found a solution or returns an error
            has_error=$(echo "$journey_response" | jq -r 'has("error")')

            if [[ "$has_error" == "true" ]]; then
                continue
            fi

            # Extract walking travel time (in seconds)
            duration=$(echo "$journey_response" | jq -r '.journeys[0].duration // 0')

            # Convert duration to distance (1.12m/s => 1.12 * duration / 1000 to get km)
            distance_km=$(awk "BEGIN {printf \"%.2f\", ($duration * $WALKING_SPEED) / 1000}")

            # Check if the stop already exists
            existing_stop_id=$(psql -t -c "SELECT stoparea_id FROM guidebook.stopareas WHERE navitia_id = '$stop_id' LIMIT 1;" | tr -d ' \n\r')

            # For new stop areas
            if [[ -z "$existing_stop_id" ]]; then
                # Get the stop_area information
                stop_info=$(curl -s -H "Authorization: $NAVITIA_API_KEY" "https://api.navitia.io/v1/places/$stop_id")
                ((NAVITIA_REQUEST_COUNT++))

                # Loop through lines
                echo "$stop_info" | jq -r '.places[0].stop_area.lines[].name' > /tmp/lines.txt
                echo "$stop_info" | jq -r '.places[0].stop_area.lines[].code' > /tmp/code.txt
                echo "$stop_info" | jq -r '.places[0].stop_area.lines[].network.name' > /tmp/network.txt
                echo "$stop_info" | jq -r '.places[0].stop_area.lines[].commercial_mode.name' > /tmp/mode.txt

                # Count the number of lines
                stop_count=$(wc -l < /tmp/lines.txt)

                # Process each line
                for ((j=1; j<=stop_count; j++)); do
                    line_full_name=$(sed "${j}q;d" /tmp/lines.txt)
                    line_name=$(sed "${j}q;d" /tmp/code.txt)
                    operator_name=$(sed "${j}q;d" /tmp/network.txt)
                    mode=$(sed "${j}q;d" /tmp/mode.txt)

                    # Create a stoparea document and save its ID
                    # shellcheck disable=SC2001
                    echo "DO \$\$ 
                    DECLARE stoparea_doc_id integer;
                    BEGIN     
                        -- Insert stopareas
                        INSERT INTO guidebook.stopareas (navitia_id, stoparea_name, line, operator, geom) 
                        VALUES ('$stop_id', '$(echo "$stop_name" | sed "s/'/''/g")', '$mode $line_name - $(echo "$line_full_name" | sed "s/'/''/g")', '$(echo "$operator_name" | sed "s/'/''/g")', ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857))
                        RETURNING stoparea_id INTO stoparea_doc_id;
                        
                        -- Insert relationship
                        INSERT INTO guidebook.waypoints_stopareas (stoparea_id, waypoint_id, distance) 
                        VALUES (stoparea_doc_id, $WAYPOINT_ID, $distance_km);
                    END \$\$;" >> "$SQL_FILE"
                done
                rm /tmp/lines.txt /tmp/code.txt /tmp/network.txt /tmp/mode.txt
            else
                # For existing stop areas
                echo "INSERT INTO guidebook.waypoints_stopareas (stoparea_id, waypoint_id, distance) VALUES ($existing_stop_id, $WAYPOINT_ID, $distance_km);" >> "$SQL_FILE"
            fi
        done

        # Cleanup
        rm /tmp/stop_names.txt /tmp/stop_ids.txt /tmp/lat.txt /tmp/lon.txt
    fi
done

# Log final progress
echo "Completed: $nb_waypoints/$nb_waypoints waypoints processed. Total Navitia API requests: $NAVITIA_REQUEST_COUNT" >> $LOG_FILE

echo "Stop time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

# Execute all SQL commands in one go
echo "Sql file length : $(wc -l < "$SQL_FILE") lines." >> $LOG_FILE

if [ -s $SQL_FILE ]; then
    psql -t -c "TRUNCATE TABLE guidebook.waypoints_stopareas RESTART IDENTITY;"
    psql -t -c "TRUNCATE TABLE guidebook.stopareas RESTART IDENTITY;"
    psql -q < $SQL_FILE
    echo "Inserts done." >> $LOG_FILE
else
    echo "SQL file empty, aborting" >> $LOG_FILE
fi