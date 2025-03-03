#!/bin/bash

# Configuration
API_KEY="eb6b9684-0714-4dd9-aba4-ce47c3368666"
SERVICE_NAME="postgresql"
DB_USER="postgres"
DB_NAME="c2corg"
WAYPOINT_ID=1050873  # ID du waypoint à tester
DISTANCE=5000 # Distance maximale à vol d'oiseau entre un waypoint et un stop_area, en mètres


# Fonction pour récupérer le dernier document_id utilisé
get_last_document_id() {
    docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "SELECT MAX(document_id) FROM guidebook.documents;" | tr -d ' '
}

# Récupérer les coordonnées du waypoint via le backend
lon_lat=$(docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
    SELECT ST_X(ST_Transform(geom, 4326)) || ',' || ST_Y(ST_Transform(geom, 4326)) 
    FROM guidebook.documents_geometries 
    WHERE document_id = $WAYPOINT_ID;
" | tr -d ' ')

# Extraire longitude et latitude
lon=$(echo "$lon_lat" | cut -d',' -f1)
lat=$(echo "$lon_lat" | cut -d',' -f2)

echo "Coordonnées extraites de la base de données: ($lon, $lat)..."


# Vérifier que les coordonnées ont bien été récupérées
if [[ -z "$lon" || -z "$lat" || "$lon" == "null" || "$lat" == "null" ]]; then
    echo "Erreur : Impossible de récupérer les coordonnées du waypoint $WAYPOINT_ID."
    exit 1
fi

echo "Traitement du waypoint ID: $WAYPOINT_ID ($lon, $lat)..."

# Requête à Navitia pour récupérer les stops proches
response=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/coord/$lon%3B$lat/places_nearby?type%5B%5D=stop_area&count=5&distance=$DISTANCE")

# Extraire tous les noms et IDs des arrêts dans des fichiers temporaires
echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .name' > /tmp/stop_names.txt
echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .id' > /tmp/stop_ids.txt
echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lat' > /tmp/lat.txt
echo "$response" | jq -r '.places_nearby[] | select(.embedded_type == "stop_area") | .stop_area.coord.lon' > /tmp/lon.txt

# Compter le nombre d'arrêts
stop_count=$(wc -l < /tmp/stop_names.txt)
echo "Nombre total d'arrêts à traiter: $stop_count"

# Parcourir les arrêts en parallèle
for ((i=1; i<=stop_count; i++)); do
    stop_name=$(sed "${i}q;d" /tmp/stop_names.txt)
    stop_id=$(sed "${i}q;d" /tmp/stop_ids.txt)
    lat_stop=$(sed "${i}q;d" /tmp/lat.txt)
    lon_stop=$(sed "${i}q;d" /tmp/lon.txt)

    echo "[$i/$stop_count] Traitement du stop: '$stop_name' avec ID: $stop_id, de coordonnées $lat_stop et $lon_stop"

    # Récupérer la durée du trajet à pied via Navitia
    journey_response=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/journeys?to=$lon%3B$lat&walking_speed=1.12&max_walking_direct_path_duration=5400&direct_path_mode%5B%5D=walking&from=$stop_id&direct_path=only_with_alternatives")

    # Vérifier si Navitia a trouvé une solution ou renvoie une erreur
    has_error=$(echo "$journey_response" | jq -r 'has("error")')

    if [[ "$has_error" == "true" ]]; then
        echo "❌ Stop ignoré : $stop_name (aucun trajet à pied trouvé)"
        continue
    fi

    # Extraire la durée du trajet à pied (en secondes)
    duration=$(echo "$journey_response" | jq -r '.journeys[0].duration // 0')

    # Convertir la durée en distance (1.12m/s => 1.12 * durée / 1000 pour obtenir en km)
    distance_km=$(awk "BEGIN {printf \"%.2f\", ($duration * 1.12) / 1000}")

    echo "✅ Stop validé : $stop_name - Distance réelle à pied : $distance_km km"

    # Vérifier si le stop existe déjà
    existing_stop_id=$(docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "SELECT document_id FROM guidebook.stops WHERE navitia_id = '$stop_id';" | tr -d ' ')

    if [[ -z "$existing_stop_id" ]]; then
        echo "Nouveau stop trouvé: $stop_name"

        # Récupérer le dernier document_id et calculer les nouveaux
        last_id=$(get_last_document_id)
        new_stop_id=$((last_id + 1))

        # Insérer dans documents et stops
        docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents (document_id, type) VALUES ($new_stop_id, 's');"

        # Faire la requête pour récupérer les informations du stop_area
        stop_info=$(curl -s -H "Authorization: $API_KEY" "https://api.navitia.io/v1/places/$stop_id")

        # Extraire les informations du stop
        line_name=$(echo "$stop_info" | jq -r '.places[0].stop_area.lines[0].code // "Non renseigné"')
        line_full_name=$(echo "$stop_info" | jq -r '.places[0].stop_area.lines[0].name // "Non renseigné"')
        operator_name=$(echo "$stop_info" | jq -r '.places[0].stop_area.lines[0].network.name // "Non renseigné"')

        echo "stop_name: $stop_name"
        echo "line_name: $line_name"
        echo "line_full_name: $line_full_name"
        echo "operator_name: $operator_name"

        # Insérer dans la base de données avec échappement des apostrophes
        safe_stop_name=$(echo "$stop_name" | sed "s/'/''/g")
        safe_line_full_name=$(echo "$line_full_name" | sed "s/'/''/g") 
        safe_operator_name=$(echo "$operator_name" | sed "s/'/''/g")

        docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.stops (document_id, navitia_id, stop_name, line, operator) VALUES ($new_stop_id, '$stop_id', '$safe_stop_name', 'Bus $line_name - $safe_line_full_name', '$safe_operator_name');"
        docker-compose exec -T $SERVICE_NAME psql -v ON_ERROR_STOP=1 -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents_geometries (version, document_id, geom, geom_detail) VALUES (1, $new_stop_id, ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857), NULL) ON CONFLICT (document_id) DO UPDATE SET geom = ST_Transform(ST_SetSRID(ST_MakePoint($lon_stop, $lat_stop), 4326), 3857);"
    else
        new_stop_id=$existing_stop_id
        echo "Stop déjà existant avec ID: $existing_stop_id"
    fi

    # Ajouter la relation dans waypoints_stops
    last_doc_id=$(get_last_document_id)
    new_waypoint_stop_id=$((last_doc_id + 1))
    echo "Création de la relation waypoint-stop avec document_id: $new_waypoint_stop_id"
    
    docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.documents (document_id, type) VALUES ($new_waypoint_stop_id, 'z');"
    docker-compose exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -c "INSERT INTO guidebook.waypoints_stops (document_id, stop_id, waypoint_id, distance) VALUES ($new_waypoint_stop_id, $new_stop_id, $WAYPOINT_ID, $distance_km);"

    echo "✅ Stop ajouté avec distance réelle à pied : $distance_km km"
    echo "----------------------------------------------"
done

# Nettoyage
rm /tmp/stop_names.txt /tmp/stop_ids.txt /tmp/lat.txt /tmp/lon.txt
