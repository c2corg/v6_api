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

API_URL="http://localhost:${API_PORT}/routes"
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
-- Réinitialiser toutes les durées calculées au début
UPDATE guidebook.routes SET calculated_duration = NULL;

-- Créer la fonction de calcul de durée
CREATE OR REPLACE FUNCTION guidebook.calculate_duration(
    activities guidebook.activity_type[],
    route_length integer,
    height_diff_up smallint,
    height_diff_down smallint,
    difficulties_height smallint DEFAULT NULL
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
    d_diff float;
    d_app float;
    t_diff float;
    t_app float;
    v_diff float := 50.0; -- Vitesse ascensionnelle des difficultés (m/h)
BEGIN
    -- Vérifier s'il s'agit d'un itinéraire de grimpe
    is_climbing := 'rock_climbing' = ANY(activities) OR 
                  'ice_climbing' = ANY(activities) OR 
                  'mountain_climbing' = ANY(activities);
    
    -- Vérification des valeurs nulles ou route_length = 0
    IF route_length IS NULL OR route_length = 0 OR height_diff_up IS NULL OR height_diff_down IS NULL THEN
        RETURN NULL;
    END IF;
    
    h := route_length::float / 1000;
    dp := height_diff_up::float;
    dn := height_diff_down::float;
    
    -- CALCUL POUR LES ITINÉRAIRES DE GRIMPE
    IF is_climbing THEN
        -- Si nous avons le dénivelé des difficultés
        IF difficulties_height IS NOT NULL AND difficulties_height > 0 THEN
            d_diff := difficulties_height::float;
            d_app := dp - d_diff;
            
            -- Temps pour parcourir les difficultés (en heures)
            t_diff := d_diff / v_diff;
            
            -- Calcul du temps d'approche (comme randonnée)
            IF d_app > 0 THEN
                -- Paramètres par défaut pour l'approche
                v := 5.0;    -- km/h (vitesse horizontale)
                a := 300.0;  -- m/h (montée)
                d := 500.0;  -- m/h (descente)
                
                dh := h / v;                 -- durée basée sur distance horizontale
                dv := (d_app / a) + (dn / d); -- durée basée sur dénivelé d'approche et descente
                
                -- Temps d'approche
                IF dh < dv THEN
                    t_app := dv + (dh / 2);
                ELSE
                    t_app := (dv / 2) + dh;
                END IF;
            ELSE
                t_app := 0;
            END IF;
            
            -- Temps total selon la formule: T = max(Tdiff, Tapp) + 0.5 * min(Tdiff, Tapp)
            dm := GREATEST(t_diff, t_app) + 0.5 * LEAST(t_diff, t_app);
        ELSE
            -- Si pas de dénivelé des difficultés, utiliser le dénivelé total
            dm := dp / v_diff;
        END IF;
    
    -- CALCUL POUR LES AUTRES ITINÉRAIRES (NON GRIMPANTS)
    ELSE
        -- Définir les paramètres selon l'activité
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
        
        -- Calcul de la durée
        dh := h / v;
        dv := (dp / a) + (dn / d);
        
        -- Calcul de la durée finale en heures
        IF dh < dv THEN
            dm := dv + (dh / 2);
        ELSE
            dm := (dv / 2) + dh;
        END IF;
    END IF;
    
    -- Convertir les heures en jours (24h = 1 jour)
    RETURN dm / 24.0;
END;
\$\$ LANGUAGE plpgsql;

-- Mise à jour des itinéraires non grimpants avec la durée calculée
UPDATE guidebook.routes r
SET calculated_duration = guidebook.calculate_duration(
    r.activities,
    r.route_length,
    r.height_diff_up,
    r.height_diff_down
)
WHERE NOT (
    'rock_climbing' = ANY(r.activities) OR 
    'ice_climbing' = ANY(r.activities) OR 
    'mountain_climbing' = ANY(r.activities)
);

-- Mise à jour des itinéraires grimpants avec la durée calculée
UPDATE guidebook.routes r
SET calculated_duration = guidebook.calculate_duration(
    r.activities,
    r.route_length,
    r.height_diff_up,
    r.height_diff_down,
    r.difficulties_height
)
WHERE (
    'rock_climbing' = ANY(r.activities) OR 
    'ice_climbing' = ANY(r.activities) OR 
    'mountain_climbing' = ANY(r.activities)
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

echo "Update completed. $update_count routes updated with calculated_duration (in days)."