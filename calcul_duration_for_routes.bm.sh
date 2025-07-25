#!/bin/bash

# Configuration
SERVICE_NAME="postgresql"

if [ -f ./.env ]; then
    # Load .env data
    export $(grep -v '^#' ./.env | xargs)
else
    echo ".env file not found!"
    exit 1
fi

PROJECT_NAME=${PROJECT_NAME:-""}           
STANDALONE=${PODMAN_ENV:-""}

OUTPUT_FILE="/tmp/routes_ids.txt"
LOG_FILE="log-duration-update.txt"
SQL_FILE="/tmp/duration_sql_commands.sql"

if [[ -n "$STANDALONE" ]]; then
    SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    cd "$SCRIPTPATH"/.. || exit
fi

echo "Start time :" > $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

# Get routes from bdd (area_id=14274)
echo "Fetching routes from database for France (area_id=14274)..." >> $LOG_FILE
$CCOMPOSE -p "${PROJECT_NAME}" exec -T $SERVICE_NAME psql -U $DB_USER -d $DB_NAME -t -c "
    SELECT r.document_id 
    FROM guidebook.routes r 
    NATURAL JOIN guidebook.area_associations aa 
    WHERE aa.area_id = 14274;
" | tr -d ' ' | grep -v '^$' > "$OUTPUT_FILE"

route_count=$(wc -l < "$OUTPUT_FILE")
echo "Found $route_count routes in France" >> $LOG_FILE

# Initialize SQL file
echo "-- SQL commands to update calculated_duration for French routes" > "$SQL_FILE"

cat << EOF >> "$SQL_FILE"
BEGIN;
-- Réinitialiser toutes les durées calculées des routes françaises au début
UPDATE guidebook.routes 
SET calculated_duration = NULL 
WHERE document_id IN (
    SELECT r.document_id 
    FROM guidebook.routes r 
    NATURAL JOIN guidebook.area_associations aa 
    WHERE aa.area_id = 14274
);

-- FONCTION POUR LES ITINÉRAIRES NON-GRIMPANTS
CREATE OR REPLACE FUNCTION guidebook.calculate_duration_non_climbing(
    activity guidebook.activity_type,
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
    min_duration_hours float := 0.5; -- 30 minutes
    max_duration_hours float := 18.0; -- 18 heures
BEGIN
    -- Gestion de la règle: si dénivelé négatif absent, égaler au positif
    IF height_diff_down IS NULL AND height_diff_up IS NOT NULL THEN
        dn := height_diff_up::float;
    ELSE
        dn := COALESCE(height_diff_down::float, 0);
    END IF;
    
    -- Convertir les autres valeurs (remplacer NULL par 0)
    h := COALESCE(route_length::float / 1000, 0);
    dp := COALESCE(height_diff_up::float, 0);
    
    -- Définir les paramètres selon l'activité (selon le cadrage)
    IF activity = 'hiking' THEN
        v := 5.0; a := 300.0; d := 500.0;
    ELSIF activity = 'snowshoeing' THEN
        v := 4.5; a := 250.0; d := 400.0;
    ELSIF activity = 'skitouring' THEN
        v := 5.0; a := 300.0; d := 1500.0;
    ELSIF activity = 'mountain_biking' THEN
        v := 15.0; a := 250.0; d := 1000.0;
    ELSE
        -- Valeurs par défaut (randonnée)
        v := 5.0; a := 300.0; d := 500.0;
    END IF;
    
    -- Calcul selon la formule DIN 33466
    dh := h / v;                    -- Composante horizontale
    dv := (dp / a) + (dn / d);      -- Composante verticale
    
    -- Application de la formule
    IF dh < dv THEN
        dm := dv + (dh / 2);
    ELSE
        dm := (dv / 2) + dh;
    END IF;
    
    -- Validation des bornes de cohérence
    IF dm < min_duration_hours OR dm > max_duration_hours THEN
        RETURN NULL;
    END IF;
    
    -- Convertir en jours
    RETURN dm / 24.0;
END;
\$\$ LANGUAGE plpgsql;

-- FONCTION POUR LES ITINÉRAIRES GRIMPANTS
CREATE OR REPLACE FUNCTION guidebook.calculate_duration_climbing(
    activity guidebook.activity_type,
    route_length integer,
    height_diff_up smallint,
    height_diff_down smallint,
    difficulties_height smallint DEFAULT NULL,
    access_height smallint DEFAULT NULL 
) RETURNS float AS \$\$
DECLARE
    h float;
    dp float;
    dn float;
    d_diff float;
    d_app float;     -- Dénivelé de l'approche
    t_diff float;    -- Temps des difficultés
    t_app float;     -- Temps de l'approche
    dh_app float;    -- Composante horizontale de l'approche
    dv_app float;    -- Composante verticale de l'approche
    v_diff float := 50.0; -- Vitesse ascensionnelle des difficultés (m/h)

    -- Paramètres pour l'approche (randonnée selon le cadrage)
    v float := 5.0;    -- km/h (vitesse horizontale)
    a float := 300.0;  -- m/h (montée)
    d float := 500.0;  -- m/h (descente)

    min_duration_hours float := 0.5; -- 30 minutes
    max_duration_hours float := 18.0; -- 18 heures
    dm float; -- Durée totale en heures
BEGIN
    -- Vérifier que c'est bien un itinéraire grimpant
    IF NOT (activity IN ('rock_climbing', 'mountain_climbing', 'ice_climbing',
                        'snow_ice_mixed', 'paragliding', 'slacklining', 'via_ferrata')) THEN
        RETURN NULL;
    END IF;

    -- Gestion de la règle: si dénivelé négatif absent, égaler au positif
    IF height_diff_down IS NULL AND height_diff_up IS NOT NULL THEN
        dn := height_diff_up::float;
    ELSE
        dn := COALESCE(height_diff_down::float, 0);
    END IF;

    -- Convertir les autres valeurs
    h := COALESCE(route_length::float / 1000, 0); -- Convertir la longueur de l'itinéraire en km
    dp := COALESCE(height_diff_up::float, 0);     -- Dénivelé positif total

    -- CAS 1: Le dénivelé des difficultés n'est pas renseigné
    IF difficulties_height IS NULL OR difficulties_height <= 0 THEN
        -- "on considère que tout l'Itinéraire est grimpant et sans approche"
        -- "Dg = dTotal / vDiff"
        IF dp <= 0 THEN
            RETURN NULL; -- Pas de données utilisables pour le calcul
        END IF;

        dm := dp / v_diff;

        -- Validation des bornes de cohérence
        IF dm < min_duration_hours OR dm > max_duration_hours THEN
            RETURN NULL;
        END IF;

        RETURN dm / 24.0; -- Convertir en jours
    END IF;

    -- CAS 2: Le dénivelé des difficultés est renseigné
    d_diff := difficulties_height::float;

    -- Vérification de cohérence basique
    IF dp > 0 AND d_diff > dp THEN
        RETURN NULL; -- Dénivelé des difficultés > dénivelé total = incohérent
    END IF;

    -- Calcul du temps des difficultés
    -- "tDiff = dDiff/vDiff"
    t_diff := d_diff / v_diff;

    -- Calcul du dénivelé de l'approche
    -- Dans cette version, 'd_app' est toujours 'dTotal - dDiff',
    -- ignorant le paramètre 'access_height' pour cette partie du calcul.
    d_app := GREATEST(dp - d_diff, 0);

    -- Calcul du temps d'approche
    IF d_app > 0 THEN
        -- "calculée de la même façon que pour la Durée de parcours de l'itinéraire à pied"
        -- "mais avec le dénivelé dApp de l'approche à la place du dénivelé total"

        dh_app := h / v;                    -- Composante horizontale de l'approche
        dv_app := (d_app / a) + (d_app / d);   -- Composante verticale de l'approche (montée + descente)

        -- Appliquer la formule DIN 33466 pour le temps d'approche
        IF dh_app < dv_app THEN
            t_app := dv_app + (dh_app / 2);
        ELSE
            t_app := (dv_app / 2) + dh_app;
        END IF;
    ELSE
        t_app := 0; -- Pas de dénivelé d'approche, donc temps d'approche nul
    END IF;

    -- Calcul final selon le cadrage
    -- "Dg = max(tDiff ,tApp) + 0,5 min(tDiff, tApp)"
    dm := GREATEST(t_diff, t_app) + 0.5 * LEAST(t_diff, t_app);

    -- Validation des bornes de cohérence
    IF dm < min_duration_hours OR dm > max_duration_hours THEN
        RETURN NULL;
    END IF;

    -- Convertir en jours (la fonction retourne des jours, mais le calcul est en heures)
    RETURN dm / 24.0;
END;
\$\$ LANGUAGE plpgsql;

-- FONCTION PRINCIPALE POUR UNE ACTIVITÉ
CREATE OR REPLACE FUNCTION guidebook.calculate_duration(
    activity guidebook.activity_type,
    route_length integer,
    height_diff_up smallint,
    height_diff_down smallint,
    difficulties_height smallint DEFAULT NULL,
    access_height smallint DEFAULT NULL
) RETURNS float AS \$\$
DECLARE
    is_climbing boolean;
BEGIN
    -- Déterminer si c'est un itinéraire de grimpe
    is_climbing := activity IN ('rock_climbing', 'mountain_climbing', 'ice_climbing', 
                                'snow_ice_mixed', 'paragliding', 'slacklining', 'via_ferrata');
    
    IF is_climbing THEN
        RETURN guidebook.calculate_duration_climbing(
            activity, route_length, height_diff_up, height_diff_down, 
            difficulties_height, access_height
        );
    ELSE
        RETURN guidebook.calculate_duration_non_climbing(
            activity, route_length, height_diff_up, height_diff_down
        );
    END IF;
END;
\$\$ LANGUAGE plpgsql;

-- FONCTION PRINCIPALE POUR MULTI-ACTIVITÉS
CREATE OR REPLACE FUNCTION guidebook.calculate_duration(
    activities guidebook.activity_type[],
    route_length integer,
    height_diff_up smallint,
    height_diff_down smallint,
    difficulties_height smallint DEFAULT NULL,
    access_height smallint DEFAULT NULL
) RETURNS float AS \$\$
DECLARE
    activity guidebook.activity_type;
    duration float;
    min_duration float := NULL;
BEGIN
    -- Pour chaque activité, calculer la durée et garder la plus courte
    FOREACH activity IN ARRAY activities LOOP
        duration := guidebook.calculate_duration(
            activity, route_length, height_diff_up, height_diff_down, 
            difficulties_height, access_height
        );
        
        -- Si cette durée est valide et plus courte que la précédente (ou c'est la première)
        IF duration IS NOT NULL AND (min_duration IS NULL OR duration < min_duration) THEN
            min_duration := duration;
        END IF;
    END LOOP;
    
    RETURN min_duration;
END;
\$\$ LANGUAGE plpgsql;

-- Mise à jour uniquement des itinéraires français avec la durée calculée
UPDATE guidebook.routes r
SET calculated_duration = guidebook.calculate_duration(
    r.activities,
    r.route_length,
    r.height_diff_up,
    r.height_diff_down,
    r.height_diff_difficulties,
    r.height_diff_access
)
WHERE r.document_id IN (
    SELECT r2.document_id 
    FROM guidebook.routes r2 
    NATURAL JOIN guidebook.area_associations aa 
    WHERE aa.area_id = 14274
);
COMMIT;
EOF

# Log progress
echo "SQL file prepared with corrected update commands for French routes." >> $LOG_FILE

# Execute all SQL commands
echo "Executing SQL commands..." >> $LOG_FILE
psql -q < "$SQL_FILE"

# Check how many French routes were updated
update_count=$(psql -t -c "
    SELECT COUNT(*) 
    FROM guidebook.routes r 
    NATURAL JOIN guidebook.area_associations aa 
    WHERE aa.area_id = 14274 AND r.calculated_duration IS NOT NULL;
")

# Check how many routes were rejected due to incoherent data
update_count=$(psql -t -c "
    SELECT COUNT(*) 
    FROM guidebook.routes r 
    NATURAL JOIN guidebook.area_associations aa 
    WHERE aa.area_id = 14274 AND r.calculated_duration IS NULL;
")

# Log completion
echo "Update completed for French routes. $update_count routes updated with calculated_duration." >> $LOG_FILE
echo "$rejected_count French routes rejected due to incoherent data." >> $LOG_FILE
echo "Stop time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE

echo "Update completed for French routes. $update_count routes updated with calculated_duration (in days)."
echo "$rejected_count French routes rejected due to incoherent data (duration < 30min or > 18h, or inconsistent elevation data)."