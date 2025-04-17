#!/bin/bash

# Configuration
SERVICE_NAME="postgresql"
DB_USER="postgres"  
DB_NAME="c2corg"

if [ -f ./.env ]; then
    # Load .env data
    export $(grep -v '^#' ./.env | xargs)
else
    echo ".env file not found!"
    exit 1
fi

PROJECT_NAME=${PROJECT_NAME:-""}           
API_PORT=${API_PORT:-6543} 
CCOMPOSE=${CCOMPOSE:-"docker-compose"}
STANDALONE=${PODMAN_ENV:-""}

API_URL="http://localhost:${API_PORT}/routes?a=14274"
OUTPUT_FILE="/tmp/routes_ids.txt"
LOG_FILE="log-duration-update.txt"
SQL_FILE="/tmp/duration_sql_commands.sql"

if [[ -n "$STANDALONE" ]]; then
    SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    cd "$SCRIPTPATH"/.. || exit
fi

echo "Start time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

# Fetch routes from API
curl -s "$API_URL" | jq -r '.documents[] | .document_id' > "$OUTPUT_FILE"

nb_routes=$(wc -l < "$OUTPUT_FILE")
echo "Total routes to process: $nb_routes"

# Initialize SQL file
echo "-- SQL commands to update calculated_duration" > "$SQL_FILE"

# Créer la fonction PostgreSQL de calcul de durée
cat << EOF > "$SQL_FILE"
-- Créer la fonction de calcul de durée
CREATE OR REPLACE FUNCTION guidebook.calculate_duration(
    activities guidebook.activity_type[],
    route_length integer,
    height_diff_up smallint,
    height_diff_down smallint
) RETURNS float AS \$\$
DECLARE
    h float;
    dp float;
    dn float;
    v float;
    a float;
    d float;
    dh float;
    dv float;
    dm float;
    is_climbing boolean;
BEGIN
    is_climbing := 'rock_climbing' = ANY(activities) OR 
                  'ice_climbing' = ANY(activities) OR 
                  'mountain_climbing' = ANY(activities);
    
    IF is_climbing THEN
        RETURN NULL;
    END IF;
    
    h := route_length::float / 1000;
    dp := height_diff_up::float;
    dn := height_diff_down::float;
    
    IF h IS NULL OR dp IS NULL OR dn IS NULL THEN
        RETURN NULL;
    END IF;
    
    IF 'hiking' = ANY(activities) THEN
        v := 5.0;
        a := 300.0;
        d := 500.0;
    ELSIF 'snowshoeing' = ANY(activities) THEN
        v := 4.5;
        a := 250.0;
        d := 400.0;
    ELSIF 'skitouring' = ANY(activities) THEN
        v := 5.0;
        a := 300.0;
        d := 1500.0;
    ELSIF 'mountain_biking' = ANY(activities) THEN
        v := 15.0;
        a := 250.0;
        d := 1000.0;
    ELSE
        v := 5.0;
        a := 300.0;
        d := 500.0;
    END IF;
    
    dh := h / v;
    dv := (dp / a) + (dn / d);
    
    IF dh < dv THEN
        dm := dv + (dh / 2);
    ELSE
        dm := (dv / 2) + dh;
    END IF;
    
    RETURN dm;
END;
\$\$ LANGUAGE plpgsql;

-- Reset all calculated durations
UPDATE guidebook.routes SET calculated_duration = NULL;

-- Update routes with calculated durations
UPDATE guidebook.routes r
SET calculated_duration = guidebook.calculate_duration(
    r.activities,
    r.route_length,
    r.height_diff_up,
    r.height_diff_down
);
EOF

# Log progress
echo "SQL file prepared with update commands." >> $LOG_FILE

# Execute all SQL commands
echo "Executing SQL commands..." >> $LOG_FILE
$CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -q -U $DB_USER -d $DB_NAME < "$SQL_FILE"

# Check how many routes were updated
update_count=$($CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
    SELECT COUNT(*) FROM guidebook.routes WHERE calculated_duration IS NOT NULL;
")

# Log completion
echo "Update completed. $update_count routes updated with calculated_duration." >> $LOG_FILE
echo "Stop time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

echo "Update completed. $update_count routes updated with calculated_duration."