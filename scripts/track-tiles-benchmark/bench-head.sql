-- pgbench: picks a random place with a track, then asks the tile of it (tile.sql follows)
SELECT floor((ST_X(geom) + 20037508.3427892) / (40075016.6855784 / 2 ^ :zoom))::int AS tx,
       floor((20037508.3427892 - ST_Y(geom)) / (40075016.6855784 / 2 ^ :zoom))::int AS ty
FROM guidebook.documents_geometries TABLESAMPLE SYSTEM (2)
WHERE geom_detail IS NOT NULL AND geom IS NOT NULL
LIMIT 1 \gset
