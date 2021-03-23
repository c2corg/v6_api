# coding: utf-8

# enum mappers: To be able to search e.g. a route with a rating between
# 'AD' and 'ED', certain enum values are converted to integers using the
# mappers listed below, and stored as number in ElasticSearch. This allows
# to do range queries.

sortable_quality_types = {
    'empty': 0,
    'draft': 1,
    'medium': 2,
    'fine': 3,
    'great': 4
}

sortable_access_times = {
    '1min': 0,
    '5min': 1,
    '10min': 2,
    '15min': 3,
    '20min': 4,
    '30min': 5,
    '45min': 6,
    '1h': 7,
    '1h30': 8,
    '2h': 9,
    '2h30': 10,
    '3h': 11,
    '3h+': 12
}

sortable_climbing_ratings = {
    '2': 0,
    '3a': 1,
    '3b': 2,
    '3c': 3,
    '4a': 4,
    '4b': 5,
    '4c': 6,
    '5a': 7,
    '5a+': 8,
    '5b': 9,
    '5b+': 10,
    '5c': 11,
    '5c+': 12,
    '6a': 13,
    '6a+': 14,
    '6b': 15,
    '6b+': 16,
    '6c': 17,
    '6c+': 18,
    '7a': 19,
    '7a+': 20,
    '7b': 21,
    '7b+': 22,
    '7c': 23,
    '7c+': 24,
    '8a': 25,
    '8a+': 26,
    '8b': 27,
    '8b+': 28,
    '8c': 29,
    '8c+': 30,
    '9a': 31,
    '9a+': 32,
    '9b': 33,
    '9b+': 34,
    '9c': 35,
    '9c+': 36
}

sortable_paragliding_ratings = {
    '1': 0,
    '2': 1,
    '3': 2,
    '4': 3,
    '5': 4
}

sortable_exposition_ratings = {
    'E1': 0,
    'E2': 1,
    'E3': 2,
    'E4': 3
}

sortable_equipment_ratings = {
    'P1': 0,
    'P1+': 1,
    'P2': 2,
    'P2+': 3,
    'P3': 4,
    'P3+': 5,
    'P4': 6,
    'P4+': 7
}

sortable_route_duration_types = {
    '1': 0,
    '2': 1,
    '3': 2,
    '4': 3,
    '5': 4,
    '6': 5,
    '7': 6,
    '8': 7,
    '9': 8,
    '10': 9,
    '10+': 10
}

sortable_ski_ratings = {
    '1.1': 0,
    '1.2': 1,
    '1.3': 2,
    '2.1': 3,
    '2.2': 4,
    '2.3': 5,
    '3.1': 6,
    '3.2': 7,
    '3.3': 8,
    '4.1': 9,
    '4.2': 10,
    '4.3': 11,
    '5.1': 12,
    '5.2': 13,
    '5.3': 14,
    '5.4': 15,
    '5.5': 16,
    '5.6': 17
}

sortable_labande_ski_ratings = {
    'S1': 0,
    'S2': 1,
    'S3': 2,
    'S4': 3,
    'S5': 4,
    'S6': 5,
    'S7': 6
}

sortable_global_ratings = {
    'F': 0,
    'F+': 1,
    'PD-': 2,
    'PD': 3,
    'PD+': 4,
    'AD-': 5,
    'AD': 6,
    'AD+': 7,
    'D-': 8,
    'D': 9,
    'D+': 10,
    'TD-': 11,
    'TD': 12,
    'TD+': 13,
    'ED-': 14,
    'ED': 15,
    'ED+': 16,
    'ED4': 17,
    'ED5': 18,
    'ED6': 19,
    'ED7': 20
}

sortable_engagement_ratings = {
    'I': 0,
    'II': 1,
    'III': 2,
    'IV': 3,
    'V': 4,
    'VI': 5
}

sortable_risk_ratings = {
    'X1': 0,
    'X2': 1,
    'X3': 2,
    'X4': 3,
    'X5': 4
}

sortable_ice_ratings = {
    '1': 0,
    '2': 1,
    '3': 2,
    '3+': 3,
    '4': 4,
    '4+': 5,
    '5': 6,
    '5+': 7,
    '6': 8,
    '6+': 9,
    '7': 10,
    '7+': 11
}

sortable_mixed_ratings = {
    'M1': 0,
    'M2': 1,
    'M3': 2,
    'M3+': 3,
    'M4': 4,
    'M4+': 5,
    'M5': 6,
    'M5+': 7,
    'M6': 8,
    'M6+': 9,
    'M7': 10,
    'M7+': 11,
    'M8': 12,
    'M8+': 13,
    'M9': 14,
    'M9+': 15,
    'M10': 16,
    'M10+': 17,
    'M11': 18,
    'M11+': 19,
    'M12': 20,
    'M12+': 21
}

sortable_exposition_rock_ratings = {
    'E1': 0,
    'E2': 1,
    'E3': 2,
    'E4': 3,
    'E5': 4,
    'E6': 5
}

sortable_aid_ratings = {
    'A0': 0,
    'A0+': 1,
    'A1': 2,
    'A1+': 3,
    'A2': 4,
    'A2+': 5,
    'A3': 6,
    'A3+': 7,
    'A4': 8,
    'A4+': 9,
    'A5': 10,
    'A5+': 11
}

sortable_via_ferrata_ratings = {
    'K1': 0,
    'K2': 1,
    'K3': 2,
    'K4': 3,
    'K5': 4,
    'K6': 5
}

sortable_hiking_ratings = {
    'T1': 0,
    'T2': 1,
    'T3': 2,
    'T4': 3,
    'T5': 4
}

sortable_snowshoe_ratings = {
    'R1': 0,
    'R2': 1,
    'R3': 2,
    'R4': 3,
    'R5': 4
}

sortable_mtb_up_ratings = {
    'M1': 0,
    'M2': 1,
    'M3': 2,
    'M4': 3,
    'M5': 4
}

sortable_mtb_down_ratings = {
    'V1': 0,
    'V2': 1,
    'V3': 2,
    'V4': 3,
    'V5': 4
}

sortable_frequentation_types = {
    'quiet': 0,
    'some': 1,
    'crowded': 2,
    'overcrowded': 3
}

sortable_condition_ratings = {
    'excellent': 0,
    'good': 1,
    'average': 2,
    'poor': 3,
    'awful': 4
}

sortable_snow_quality_ratings = {
    'excellent': 0,
    'good': 1,
    'average': 2,
    'poor': 3,
    'awful': 4
}

sortable_snow_quantity_ratings = {
    'excellent': 0,
    'good': 1,
    'average': 2,
    'poor': 3,
    'awful': 4
}

sortable_glacier_ratings = {
    'easy': 0,
    'possible': 1,
    'difficult': 2,
    'impossible': 3
}

sortable_severities = {
    'severity_no': 0,
    '1d_to_3d': 1,
    '4d_to_1m': 2,
    '1m_to_3m': 3,
    'more_than_3m': 4,
}

sortable_avalanche_levels = {
    'level_na': 0,
    'level_1': 1,
    'level_2': 2,
    'level_3': 3,
    'level_4': 4,
    'level_5': 5
}

sortable_avalanche_slopes = {
    'slope_lt_30': 0,
    'slope_30_35': 1,
    'slope_35_40': 2,
    'slope_40_45': 3,
    'slope_gt_45': 4
}
