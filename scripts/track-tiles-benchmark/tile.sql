-- One vector tile of the tracks of the outings: what an API endpoint (or a tile
-- generator) would run. Variables: :zoom :tx :ty (the XYZ scheme). Needs PostGIS 3
-- (ST_TileEnvelope, ST_AsMVTGeom, ST_AsMVT).
--
-- The tracks are simplified to one unit of the tile (1/4096 of its width) and
-- clipped to the tile with a margin of 64 units. No property: the geometry
-- alone, which is the smallest tile (a property such as an activity or a year
-- would be added to filter on the client).
WITH env AS (
    SELECT ST_TileEnvelope(:zoom, :tx, :ty) AS tile,
           40075016.6855784 / 2 ^ :zoom / 4096 AS unit
), feats AS (
    SELECT ST_AsMVTGeom(
               ST_Simplify(ST_Force2D(g.geom_detail), env.unit),
               env.tile, 4096, 64, true
           ) AS geom
    FROM guidebook.documents_geometries g
    JOIN guidebook.outings o ON o.document_id = g.document_id
    JOIN guidebook.documents d ON d.document_id = g.document_id
    CROSS JOIN env
    WHERE g.geom_detail IS NOT NULL
      AND d.redirects_to IS NULL
      AND g.geom_detail && ST_Expand(env.tile, env.unit * 64)
)
SELECT length(ST_AsMVT(feats.*, 'tracks', 4096, 'geom')) AS bytes,
       count(*) AS features
FROM feats
WHERE geom IS NOT NULL;
