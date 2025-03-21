#!/bin/bash

# Configuration
API_KEY="eb6b9684-0714-4dd9-aba4-ce47c3368666"
SERVICE_NAME="postgresql"
DB_USER="postgres"  
DB_NAME="c2corg"
MAXDISTANCEWAYPOINT2STOPAREA=5000 # Maximum distance between a waypoint and a stop area, in meters
WALKING_SPEED=1.12 # Walking speed in m/s
MAXSTOPAREA=5

DURATION=$(echo "scale=0; $MAXDISTANCEWAYPOINT2STOPAREA / $WALKING_SPEED" | bc)

PROJECT_NAME=${PROJECT_NAME:-""}           
API_PORT=${API_PORT:-6543} 
CCOMPOSE=${CCOMPOSE:-"podman-compose"}
STANDALONE=${PODMAN_ENV:-""}

API_URL="http://localhost:${API_PORT}/waypoints?wtyp=access&a=14328&offset=0&limit=10000"
OUTPUT_FILE="/tmp/waypoints_ids.txt"
LOG_FILE="log-navitia.txt"
NAVITIA_REQUEST_COUNT=0
SQL_FILE="/tmp/sql_commands.sql"

if [[ -n "$STANDALONE" ]]; then
    SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    cd "$SCRIPTPATH"/.. || exit
fi

echo "Start time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

# Fetch waypoints from API
curl -s "$API_URL" | jq -r '.documents[] | .document_id' > "$OUTPUT_FILE"

nb_waypoints=$(wc -l < "$OUTPUT_FILE")

# Initialize SQL file
> "$SQL_FILE"

for ((k=1; k<=nb_waypoints; k++)); do
    # Log progress every 10 waypoints
    if (( k % 10 == 0 )) || (( k == 1 )); then
        echo "Progress: $k/$nb_waypoints waypoints processed. Navitia API requests: $NAVITIA_REQUEST_COUNT" >> $LOG_FILE
    fi

    WAYPOINT_ID=$(sed "${k}q;d" /tmp/waypoints_ids.txt)

    # Get waypoint coordinates from backend
    lon_lat=$($CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
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
    response=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/coord/$lon%3B$lat/places_nearby?type%5B%5D=stop_area&count=$MAXSTOPAREA&distance=$MAXDISTANCEWAYPOINT2STOPAREA")
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
            journey_response=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/journeys?to=$lon%3B$lat&walking_speed=$WALKING_SPEED&max_walking_direct_path_duration=$DURATION&direct_path_mode%5B%5D=walking&from=$stop_id&direct_path=only_with_alternatives")
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
            existing_stop_id=$($CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "SELECT document_id FROM guidebook.stopareas WHERE navitia_id = '$stop_id' LIMIT 1;" | tr -d ' \n\r')

            # For new stop areas
            if [[ -z "$existing_stop_id" ]]; then
                # Get the stop_area information
                stop_info=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/places/$stop_id")
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
                    echo "DO \$\$ 
                    DECLARE stoparea_doc_id integer;
                    DECLARE relation_doc_id integer;
                    BEGIN
                        INSERT INTO guidebook.documents (type) VALUES ('s') RETURNING document_id INTO stoparea_doc_id;
                        
                        INSERT INTO guidebook.stopareas (document_id, navitia_id, stoparea_name, line, operator) 
                        VALUES (stoparea_doc_id, '$stop_id', '$(echo "$stop_name" | sed "s/'/''/g")', '$mode $line_name - $(echo "$line_full_name" | sed "s/'/''/g")', '$(echo "$operator_name" | sed "s/'/''/g")');
                        
                        INSERT INTO guidebook.documents_geometries (version, document_id, geom, geom_detail) 
                        VALUES (1, stoparea_doc_id, ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857), NULL) 
                        ON CONFLICT (document_id) DO UPDATE SET geom = ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857);
                        
                        -- Create relation document
                        INSERT INTO guidebook.documents (type) VALUES ('z') RETURNING document_id INTO relation_doc_id;
                        
                        -- Insert relationship
                        INSERT INTO guidebook.waypoints_stopareas (document_id, stoparea_id, waypoint_id, distance) 
                        VALUES (relation_doc_id, stoparea_doc_id, $WAYPOINT_ID, $distance_km);
                    END \$\$;" >> "$SQL_FILE"
                done
            else
                # For existing stop areas
                echo "DO \$\$ 
                DECLARE relation_doc_id integer;
                BEGIN
                    -- Create relation document
                    INSERT INTO guidebook.documents (type) VALUES ('z') RETURNING document_id INTO relation_doc_id;
                    
                    -- Insert relationship
                    INSERT INTO guidebook.waypoints_stopareas (document_id, stoparea_id, waypoint_id, distance) 
                    VALUES (relation_doc_id, $existing_stop_id, $WAYPOINT_ID, $distance_km);
                END \$\$;" >> "$SQL_FILE"
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
$CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME < /tmp/sql_commands.sql

echo "Inserts done." >> $LOG_FILE
