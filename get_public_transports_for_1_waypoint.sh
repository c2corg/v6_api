#!/bin/bash

# Configuration
API_KEY="eb6b9684-0714-4dd9-aba4-ce47c3368666"
SERVICE_NAME="postgresql"
DB_USER="postgres"  
DB_NAME="c2corg"
MAXDISTANCEWAYPOINT2STOPAREA=5000 # Maximum distance between a waypoint and a stop area, in meters
WALKING_SPEED=1.12 # Walking speed in m/s
MAXSTOPAREA=5
WAYPOINT_ID=$1

DURATION=$(echo "scale=0; $MAXDISTANCEWAYPOINT2STOPAREA / $WALKING_SPEED" | bc)

PROJECT_NAME=${PROJECT_NAME:-""}           
API_PORT=${API_PORT:-6543} 

NAVITIA_REQUEST_COUNT=0
# Function to get the last document_id used
get_last_document_id() {
    docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "SELECT MAX(document_id) FROM guidebook.documents;" | tr -d ' '
}

# Get waypoint coordinates from backend
lon_lat=$(docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
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
    echo "Stop areas found for waypoint $WAYPOINT_ID"
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
        existing_stop_id=$(docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "SELECT document_id FROM guidebook.stopareas WHERE navitia_id = '$stop_id' LIMIT 1;" | tr -d ' \n\r')

        if [[ -z "$existing_stop_id" ]]; then
            # Get the stop_area information
            stop_info=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/places/$stop_id")
            ((NAVITIA_REQUEST_COUNT++))

            # Loop through lines
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].name' > /tmp/lines.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].code' > /tmp/code.txt
            echo "$stop_info" | jq -r '.places[0].stop_area.lines[].network.name' > /tmp/network.txt

            # Count the number of lines
            stop_count=$(wc -l < /tmp/lines.txt)

            # Process each line
            for ((j=1; j<=stop_count; j++)); do
                line_full_name=$(sed "${j}q;d" /tmp/lines.txt)
                line_name=$(sed "${j}q;d" /tmp/code.txt)
                operator_name=$(sed "${j}q;d" /tmp/network.txt)

                # Get the last document_id and calculate new ones
                last_id=$(get_last_document_id)
                new_stop_id=$((last_id + 1))

                # Insert into documents and stops - add -q for quiet mode
                docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents (document_id, type) VALUES ($new_stop_id, 's');"

                # Insert into database with apostrophe escaping
                safe_stop_name=$(echo "$stop_name" | sed "s/'/''/g")
                safe_line_full_name=$(echo "$line_full_name" | sed "s/'/''/g") 
                safe_operator_name=$(echo "$operator_name" | sed "s/'/''/g")

                docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.stopareas (document_id, navitia_id, stoparea_name, line, operator) VALUES ($new_stop_id, '$stop_id', '$safe_stop_name', 'Bus $line_name - $safe_line_full_name', '$safe_operator_name');"
                docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -v ON_ERROR_STOP=1 -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents_geometries (version, document_id, geom, geom_detail) VALUES (1, $new_stop_id, ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857), NULL) ON CONFLICT (document_id) DO UPDATE SET geom = ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857);"
                
                # Add relationship in waypoints_stops
                last_doc_id=$(get_last_document_id)
                new_waypoint_stop_id=$((last_doc_id + 1))
                
                docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents (document_id, type) VALUES ($new_waypoint_stop_id, 'z');"
                docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.waypoints_stopareas (document_id, stoparea_id, waypoint_id, distance) VALUES ($new_waypoint_stop_id, $new_stop_id, $WAYPOINT_ID, $distance_km);"
            done
        else
            new_stop_id=$(echo "$existing_stop_id" | tr -d '\n\r')
            last_doc_id=$(get_last_document_id | tr -d '\n\r')
            new_waypoint_stop_id=$((last_doc_id + 1))
            
            docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents (document_id, type) VALUES ($new_waypoint_stop_id, 'z');"
            docker-compose -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.waypoints_stopareas (document_id, stoparea_id, waypoint_id, distance) VALUES ($new_waypoint_stop_id, $new_stop_id, $WAYPOINT_ID, $distance_km);"
        fi
    done

    echo "Stop areas added in DB."

    # Cleanup
    rm /tmp/stop_names.txt /tmp/stop_ids.txt /tmp/lat.txt /tmp/lon.txt
fi

