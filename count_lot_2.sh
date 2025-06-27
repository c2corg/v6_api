#!/bin/bash

# Configuration
SERVICE_NAME="postgresql"
DB_USER="postgres"  
DB_NAME="c2corg"

# Charger les variables d'environnement si disponibles
if [ -f ./.env ]; then
    export $(grep -v '^#' ./.env | xargs)
else
    echo ".env file not found, using default values"
fi

PROJECT_NAME=${PROJECT_NAME:-""}           
CCOMPOSE=${CCOMPOSE:-"docker-compose"}
STANDALONE=${PODMAN_ENV:-""}

# Si en mode standalone, se positionner correctement
if [[ -n "$STANDALONE" ]]; then
    SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    cd "$SCRIPTPATH"/.. || exit
fi

echo "Counting routes with exactly 1 'access' waypoint that is accessible by public transport..."

# Exécuter la requête SQL modifiée
count=$($CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
    SELECT COUNT(*)
    FROM (
        SELECT r.child_document_id
        FROM (
            SELECT a.child_document_id, a.parent_document_id
            FROM guidebook.associations a
            JOIN guidebook.waypoints w ON a.parent_document_id = w.document_id
            WHERE a.parent_document_type = 'w' 
            AND a.child_document_type = 'r'
            AND w.waypoint_type = 'access'
        ) r
        JOIN guidebook.waypoints_stopareas ws ON r.parent_document_id = ws.waypoint_id
        GROUP BY r.child_document_id
        HAVING COUNT(r.parent_document_id) = 1
    ) AS routes_with_one_public_transport_access;
" | tr -d ' ')

echo "Number of routes with exactly 1 'access' waypoint accessible by public transport: $count"