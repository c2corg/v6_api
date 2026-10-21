-- Links the Navitia stops (guidebook.stopareas) to the imported GTFS stops
-- (guidebook.transport_stops): fills transport_stops.navitia_ids.
--
-- Used by c2corg_api/transport/linking.py and by the Navitia import script
-- (scripts/public_transport/get_public_transports*.sh): psql -v max_distance=50
--
-- One statement per paragraph, each ends with a semicolon at the end of a line.

-- 0. start again
UPDATE guidebook.transport_stops SET navitia_ids = '{}'
WHERE navitia_ids <> '{}';

-- 1. by id: the Navitia id ends with the id of the GTFS stop (or of one of its
-- platforms, or their code):
--   stop_area:R74:Navitia:FR:74273:ZE:92676:HAUTExSAVOIE
--   <-> FR:74273:ZE:92676:HAUTExSAVOIE
-- (the distance only limits the stops compared)
WITH navitia AS (
    SELECT DISTINCT ON (navitia_id) navitia_id, geom
    FROM guidebook.stopareas
), matched AS (
    SELECT t.stop_pk, n.navitia_id
    FROM navitia n
    JOIN guidebook.transport_stops t ON ST_DWithin(n.geom, t.geom, 3000)
    WHERE EXISTS (
        SELECT 1 FROM unnest(t.ref_ids) r
        WHERE right(n.navitia_id, length(r) + 1) = ':' || r)
)
UPDATE guidebook.transport_stops t
SET navitia_ids = m.ids
FROM (
    SELECT stop_pk, array_agg(DISTINCT navitia_id) AS ids
    FROM matched GROUP BY stop_pk
) m
WHERE t.stop_pk = m.stop_pk;

-- 2. by line and distance: a Navitia stop not matched by its id, very close
-- (:max_distance meters) to a GTFS stop served by one of its lines
-- ("Bus 12 - Ligne 12": the code of the line is the second word)
WITH navitia AS (
    SELECT navitia_id,
           (array_agg(geom))[1] AS geom,
           array_agg(split_part(line, ' ', 2)) AS codes
    FROM guidebook.stopareas s
    WHERE NOT EXISTS (
        SELECT 1 FROM guidebook.transport_stops x
        WHERE x.navitia_ids @> ARRAY[s.navitia_id])
    GROUP BY navitia_id
), matched AS (
    SELECT t.stop_pk, n.navitia_id
    FROM navitia n
    JOIN guidebook.transport_stops t ON ST_DWithin(
        n.geom, t.geom,
        :max_distance / cos(radians(ST_Y(ST_Transform(n.geom, 4326)))))
    WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements(t.details->'lines') l
        WHERE l->>'short_name' = ANY (n.codes))
)
UPDATE guidebook.transport_stops t
SET navitia_ids = (
    SELECT array_agg(DISTINCT id)
    FROM unnest(t.navitia_ids || m.ids) id)
FROM (
    SELECT stop_pk, array_agg(DISTINCT navitia_id) AS ids
    FROM matched GROUP BY stop_pk
) m
WHERE t.stop_pk = m.stop_pk;
