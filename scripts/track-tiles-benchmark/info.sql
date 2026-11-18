SELECT version();
SELECT postgis_full_version();
SELECT pg_size_pretty(pg_total_relation_size('guidebook.documents_geometries')) AS geometries_total,
       pg_size_pretty(pg_relation_size('guidebook.documents_geometries')) AS geometries_heap;
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents_geometries';
SELECT count(*) AS outings,
       count(*) FILTER (WHERE g.geom_detail IS NOT NULL) AS outings_with_track
FROM guidebook.outings o JOIN guidebook.documents_geometries g USING (document_id);
-- the size of the tracks, on a 2 % sample of the blocks (reading all of them would load the database)
SELECT count(*) AS sampled_tracks,
       round(avg(ST_NPoints(geom_detail))) AS avg_points,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_NPoints(geom_detail)) AS median_points,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY ST_NPoints(geom_detail)) AS p95_points,
       max(ST_NPoints(geom_detail)) AS max_points
FROM guidebook.documents_geometries TABLESAMPLE SYSTEM (2)
WHERE geom_detail IS NOT NULL;
SELECT name, setting FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem', 'effective_cache_size', 'max_parallel_workers_per_gather', 'jit');
