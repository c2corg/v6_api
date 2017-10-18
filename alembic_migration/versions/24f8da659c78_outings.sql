
DROP TABLE IF EXISTS tmp_tbl;

CREATE TEMP TABLE tmp_tbl AS
SELECT * from guidebook.outings
WHERE 1=2;


INSERT INTO tmp_tbl(
    activities,
    date_start,
    date_end,
    frequentation,
    participant_count,
    elevation_min,
    elevation_max,
    elevation_access,
    elevation_up_snow,
    elevation_down_snow,
    height_diff_up,
    height_diff_down,
    length_total,
    partial_trip,
    public_transport,
    access_condition,
    lift_status,
    condition_rating,
    snow_quantity,
    snow_quality,
    glacier_rating,
    avalanche_signs,
    hut_status,
    document_id,
    disable_comments,
    ski_rating,
    labande_global_rating,
    global_rating,
    snowshoe_rating,
    hiking_rating,
      height_diff_difficulties,
    engagement_rating,
    equipment_rating,
    rock_free_rating,
    ice_rating,
    via_ferrata_rating,
    mtb_up_rating,
    mtb_down_rating
    )
SELECT
    o.activities,
    o.date_start,
    o.date_end,
    o.frequentation,
    o.participant_count,
    o.elevation_min,
    o.elevation_max,
    o.elevation_access,
    o.elevation_up_snow,
    o.elevation_down_snow,
    o.height_diff_up,
    o.height_diff_down,
    o.length_total,
    o.partial_trip,
    o.public_transport,
    o.access_condition,
    o.lift_status,
    o.condition_rating,
    o.snow_quantity,
    o.snow_quality,
    o.glacier_rating,
    o.avalanche_signs,
    o.hut_status,
    o.document_id,
    o.disable_comments,
    CASE
	    WHEN 'skitouring' = ANY(o.activities)
            THEN max(r.ski_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'skitouring' = ANY(o.activities)
            THEN max(r.labande_global_rating)
        ELSE NULL
    END,
    CASE
        WHEN ('snow_ice_mixed' = ANY(o.activities) OR
              'mountain_climbing' = ANY(o.activities) OR
              'rock_climbing' = ANY(o.activities)
        )
            THEN max(r.global_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'snowshoeing' = ANY(o.activities)
            THEN max(r.snowshoe_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'hiking' = ANY(o.activities)
            THEN max(r.hiking_rating)
        ELSE NULL
    END,
    CASE
	    WHEN ('snow_ice_mixed' = ANY(o.activities) OR
              'mountain_climbing' = ANY(o.activities))
        THEN max(r.height_diff_difficulties)
        ELSE NULL
    END,
    CASE
        WHEN ('snow_ice_mixed' = ANY(o.activities) OR
              'mountain_climbing' = ANY(o.activities)
              )
              THEN max(r.engagement_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'rock_climbing' = ANY(o.activities)
            THEN max(r.equipment_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'rock_climbing' = ANY(o.activities)
	        THEN max(r.rock_free_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'ice_climbing' = ANY(o.activities)
            THEN max(r.ice_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'via_ferrata' = ANY(o.activities)
            THEN max(r.via_ferrata_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'mountain_biking' = ANY(o.activities)
            THEN max(r.mtb_up_rating)
        ELSE NULL
    END,
    CASE
        WHEN 'mountain_biking' = ANY(o.activities)
	        THEN max(r.mtb_down_rating)
        ELSE NULL
    END
	
FROM guidebook.routes r
JOIN guidebook.associations as a ON (r.document_id =
     a.parent_document_id)
JOIN guidebook.outings as o ON (a.child_document_id =
    o.document_id)
WHERE a.parent_document_type = 'r' AND
      a.child_document_type = 'o'
GROUP BY o.document_id, o.activities, o.date_start, o.date_end, o.frequentation,
    o.participant_count,
    o.elevation_min,
    o.elevation_max,
    o.elevation_access,
    o.elevation_up_snow,
    o.elevation_down_snow,
    o.height_diff_up,
    o.height_diff_down,
    o.length_total,
    o.partial_trip,
    o.public_transport,
    o.access_condition,
    o.lift_status,
    o.condition_rating,
    o.snow_quantity,
    o.snow_quality,
    o.glacier_rating,
    o.avalanche_signs,
    o.hut_status,
    o.document_id,
    o.disable_comments;


TRUNCATE guidebook.outings;

INSERT INTO guidebook.outings
SELECT * FROM tmp_tbl;
