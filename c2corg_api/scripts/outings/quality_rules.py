"""The rules of the quality ("complétude") of the outings, as the UI computes it.

The UI computes the quality of an outing when it is saved, in
`c2c_ui/src/js/document-quality.ts`. This module is a copy of those rules in
Python, so that `recompute_quality.py` can apply them to the outings already
saved.

One function per version of the rules, in `RULES`, the latest last:

- the latest is the one of the UI: the outings are recomputed with it;
- the older ones tell whether the quality of an outing was computed (it is the
  one an older version gives) or chosen by its author (it is not): a chosen
  quality is kept.

When the rules of the UI change:

1. add a function for the new rules at the end of `RULES` (never change an
   existing one: the outings saved with it would look chosen);
2. add tests in `c2corg_api/tests/scripts/outings/test_quality_rules.py`, with
   the cases of the UI tests (`c2c_ui/src/js/document-quality.spec.ts`);
3. run `recompute_quality.py` once the UI is deployed.
"""

import json

QUALITY_TYPES = ['empty', 'draft', 'medium', 'fine', 'great']


class OutingData:
    """What the rules read of an outing, in one of its locales."""

    def __init__(self, outing, locale, has_track, image_count):
        self.activities = outing.activities or []
        self.access_condition = outing.access_condition
        self.elevation_access = outing.elevation_access
        self.avalanche_signs = outing.avalanche_signs or []
        self.condition_rating = outing.condition_rating
        self.elevation_up_snow = outing.elevation_up_snow
        self.elevation_down_snow = outing.elevation_down_snow
        self.snow_quantity = outing.snow_quantity
        self.snow_quality = outing.snow_quality
        self.length_total = outing.length_total
        self.glacier_rating = outing.glacier_rating
        # read apart: the tracks are not loaded
        self.has_track = has_track
        self.image_count = image_count
        self.locale = locale

    def text(self, field):
        """Return the text of a field of the locale, or None."""
        return getattr(self.locale, field, None)


def _quality_from_score(score):
    if score < 1:
        return 'empty'
    if score < 2:
        return 'draft'
    if score < 3:
        return 'medium'
    return 'fine'  # never great


def _has_activities(outing, activities):
    return any(activity in outing.activities for activity in activities)


def _has_snow_info(outing):
    return bool(
        outing.elevation_up_snow
        or outing.elevation_down_snow
        or outing.snow_quantity
        or outing.snow_quality
        or outing.length_total
        or outing.glacier_rating
    )


def _first_condition_level(outing):
    levels = outing.text('conditions_levels')
    if not levels:
        return None
    try:
        levels = json.loads(levels)
    except ValueError:
        return None
    if not isinstance(levels, list) or not levels or not isinstance(levels[0], dict):
        return None
    return levels[0]


def _has_condition_level(outing, has_text):
    if has_text(outing, 'conditions'):
        return True
    level = _first_condition_level(outing)
    return bool(
        level
        and (
            level.get('level_place')
            or level.get('level_comment')
            or level.get('level_snow_height_total')
            or level.get('level_snow_height_soft')
        )
    )


def _best(outing, scores):
    """Return the best score of the activities of the outing."""
    return max(
        [
            get_score(outing)
            for activities, get_score in scores
            if _has_activities(outing, activities)
        ],
        default=0,
    )


# Version 1: the rules of the UI until November 2026


def _v1_text(outing, field):
    # a field filled in, even with spaces
    return bool(outing.text(field))


def _v1_route_info(outing):
    return outing.has_track or _v1_text(outing, 'route_description')


def _v1_ski(outing):
    score = 0.5 if _v1_route_info(outing) else 0
    score += 0.5 if _has_snow_info(outing) else 0
    if (
        outing.access_condition
        and outing.access_condition != 'snowy'
        and outing.elevation_access
    ) or (
        outing.access_condition == 'snowy'
        and outing.elevation_access
        and _v1_text(outing, 'access_comment')
    ):
        score += 0.5
    if any(sign != 'no' for sign in outing.avalanche_signs) and _v1_text(
        outing, 'avalanches'
    ):
        score += 0.5
    score += 0.5 if _v1_text(outing, 'description') else 0
    score += 0.5 if _v1_text(outing, 'weather') else 0
    score += 0.5 if outing.condition_rating else 0
    if _has_condition_level(outing, _v1_text):
        return score + 1
    return min(score, 2)


def _v1_ice(outing):
    score = 0.5 if _v1_route_info(outing) else 0
    score += 0.5 if outing.condition_rating else 0
    score += 1 if _v1_text(outing, 'description') else 0
    score += 0.5 if _v1_text(outing, 'timing') else 0
    score += 0.5 if _v1_text(outing, 'weather') else 0
    if _has_condition_level(outing, _v1_text):
        return score + 1.5
    return min(score, 2)


def _v1_climbing(outing):
    score = 0.5 if _v1_route_info(outing) else 0
    score += 1 if _v1_text(outing, 'description') else 0
    score += 0.5 if _v1_text(outing, 'timing') else 0
    score += 0.5 if _v1_text(outing, 'weather') else 0
    if _v1_text(outing, 'conditions'):
        return score + 2
    return min(score, 2)


_V1_SCORES = [
    (['skitouring', 'snowshoeing'], _v1_ski),
    (['snow_ice_mixed', 'ice_climbing', 'mountain_climbing'], _v1_ice),
    (
        [
            'rock_climbing',
            'hiking',
            'mountain_biking',
            'via_ferrata',
            'paragliding',
            'slacklining',
        ],
        _v1_climbing,
    ),
]


def quality_v1(outing):
    return _quality_from_score(_best(outing, _V1_SCORES))


# Version 2 (November 2026): never empty with a text, the track and the images
# count, the key information of each activity (c2c_ui#5065)

# the text fields of an outing (title and participants are not about the outing)
_V2_TEXT_FIELDS = [
    'summary',
    'description',
    'route_description',
    'conditions',
    'access_comment',
    'hut_comment',
    'avalanches',
    'weather',
    'timing',
]


def _v2_text(outing, field):
    # a few words are enough, spaces are not
    value = outing.text(field)
    return isinstance(value, str) and value.strip() != ''


def _v2_route(outing):
    score = 0.5 if _v2_text(outing, 'route_description') else 0
    score += 0.5 if outing.has_track else 0
    score += 0.5 if outing.image_count else 0
    return score


def _v2_snow(outing):
    score = _v2_route(outing)
    score += 0.5 if _has_snow_info(outing) else 0
    if (
        outing.access_condition
        and outing.access_condition != 'snowy'
        and outing.elevation_access
    ) or (
        outing.access_condition == 'snowy'
        and outing.elevation_access
        and _v2_text(outing, 'access_comment')
    ):
        score += 0.5
    if any(sign != 'no' for sign in outing.avalanche_signs) and _v2_text(
        outing, 'avalanches'
    ):
        score += 0.5
    score += 0.5 if _v2_text(outing, 'description') else 0
    score += 0.5 if _v2_text(outing, 'weather') else 0
    score += 0.5 if outing.condition_rating else 0
    if _has_condition_level(outing, _v2_text):
        return score + 1
    return min(score, 2)


def _v2_ice(outing):
    score = _v2_route(outing)
    score += 0.5 if outing.condition_rating else 0
    score += 1 if _v2_text(outing, 'description') else 0
    score += 0.5 if _v2_text(outing, 'timing') else 0
    score += 0.5 if _v2_text(outing, 'weather') else 0
    if _has_condition_level(outing, _v2_text):
        return score + 1.5
    return min(score, 2)


def _v2_climbing(outing):
    score = _v2_route(outing)
    score += 1 if _v2_text(outing, 'conditions') else 0
    score += 1 if _v2_text(outing, 'description') else 0
    score += 0.5 if _v2_text(outing, 'timing') else 0
    score += 0.5 if _v2_text(outing, 'weather') else 0
    if _v2_text(outing, 'conditions') or _v2_text(outing, 'description'):
        return score
    return min(score, 2)


def _v2_paragliding(outing):
    score = _v2_route(outing)
    score += 1 if _v2_text(outing, 'conditions') else 0
    score += 1 if _v2_text(outing, 'description') else 0
    score += 1 if _v2_text(outing, 'weather') else 0
    score += 0.5 if _v2_text(outing, 'timing') else 0
    if any(
        _v2_text(outing, field) for field in ('conditions', 'weather', 'description')
    ):
        return score
    return min(score, 2)


_V2_SCORES = [
    (['skitouring', 'snowshoeing'], _v2_snow),
    (['snow_ice_mixed', 'ice_climbing', 'mountain_climbing'], _v2_ice),
    (
        ['rock_climbing', 'via_ferrata', 'slacklining', 'hiking', 'mountain_biking'],
        _v2_climbing,
    ),
    (['paragliding'], _v2_paragliding),
]


def quality_v2(outing):
    score = _best(outing, _V2_SCORES)
    if any(_v2_text(outing, field) for field in _V2_TEXT_FIELDS):
        score = max(score, 1)
    return _quality_from_score(score)


# the versions of the rules, the latest (the one of the UI) last
RULES = [quality_v1, quality_v2]


def best_quality(qualities):
    """Return the best of the given qualities."""
    return max(qualities, key=QUALITY_TYPES.index)


def recomputed_quality(stored_quality, outings_by_locale):
    """Return the quality an outing gets with the latest rules, or None to keep it.

    `outings_by_locale` gives the `OutingData` of the outing in each of its
    locales. The quality is kept when it was chosen: "great" (never computed),
    or a quality no version of the rules gives in any of the locales. Else, it
    is the best quality the latest rules give in the locales where the stored
    quality was computed.
    """
    if stored_quality == 'great':
        return None

    computed_in = [
        outing
        for outing in outings_by_locale
        if any(rules(outing) == stored_quality for rules in RULES)
    ]
    if not computed_in:
        return None

    latest = RULES[-1]
    quality = best_quality([latest(outing) for outing in computed_in])
    return None if quality == stored_quality else quality
