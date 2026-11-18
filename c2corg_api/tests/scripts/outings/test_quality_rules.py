"""The rules of the quality of the outings: the cases of the UI tests.

The latest rules must give what `c2c_ui/src/js/document-quality.spec.ts`
expects: keep both tests in step.
"""

from types import SimpleNamespace

from c2corg_api.scripts.outings.quality_rules import (
    OutingData,
    quality_v1,
    quality_v2,
    recomputed_quality,
)

FIELDS = [
    'access_condition',
    'elevation_access',
    'avalanche_signs',
    'condition_rating',
    'elevation_up_snow',
    'elevation_down_snow',
    'snow_quantity',
    'snow_quality',
    'length_total',
    'glacier_rating',
]


def outing(activities, locale=None, track=False, images=0, **attributes):
    values = dict.fromkeys(FIELDS)
    values.update(attributes)
    return OutingData(
        SimpleNamespace(activities=activities, **values),
        SimpleNamespace(**(locale or {})),
        track,
        images,
    )


def test_empty():
    assert quality_v2(outing(['rock_climbing'])) == 'empty'
    assert quality_v2(outing(['rock_climbing'], {'description': '  \n '})) == 'empty'


def test_never_empty_with_a_text():
    for activity in [
        'skitouring',
        'mountain_climbing',
        'rock_climbing',
        'hiking',
        'paragliding',
    ]:
        for field in ['route_description', 'access_comment', 'timing', 'weather']:
            assert (
                quality_v2(outing([activity], {field: 'plan an Abalakov'})) == 'draft'
            )
    # the old rules: the outings of the forum, empty with a route description
    assert quality_v1(outing(['rock_climbing'], {'route_description': 'x'})) == 'empty'


def test_track_and_images():
    locale = {'route_description': 'the left variant'}
    assert quality_v2(outing(['rock_climbing'], locale)) == 'draft'
    assert (
        quality_v2(outing(['rock_climbing'], locale, track=True, images=2)) == 'draft'
    )
    locale['description'] = 'abrasive rock'
    assert (
        quality_v2(outing(['rock_climbing'], locale, track=True, images=2)) == 'medium'
    )


def test_rock_climbing_personal_comment():
    detailed = {'route_description': 'approach', 'description': 'equipment, rock'}
    assert quality_v2(outing(['rock_climbing'], detailed, images=1)) == 'medium'
    # it was a draft
    assert quality_v1(outing(['rock_climbing'], detailed, images=1)) == 'draft'

    weather_only = {'conditions': 'not too hot', 'weather': 'cumulus', 'timing': '5h'}
    assert quality_v2(outing(['rock_climbing'], weather_only)) == 'medium'
    # it was fine
    assert quality_v1(outing(['rock_climbing'], weather_only)) == 'fine'

    both = {**detailed, **weather_only}
    assert quality_v2(outing(['rock_climbing'], both, images=1)) == 'fine'


def test_key_information_caps_at_medium():
    locale = {
        'route_description': 'route',
        'description': 'comment',
        'weather': 'sunny',
        'timing': '5h',
    }
    assert quality_v2(outing(['mountain_climbing'], locale, True, 1)) == 'medium'
    with_conditions = {**locale, 'conditions': 'icy couloir'}
    assert quality_v2(outing(['mountain_climbing'], with_conditions, True)) == 'fine'

    ski = {'snow_quality': 'good', 'condition_rating': 'good'}
    assert quality_v2(outing(['skitouring'], locale, True, 1, **ski)) == 'medium'
    with_snow = {**locale, 'conditions': 'powder above 2000 m'}
    assert quality_v2(outing(['skitouring'], with_snow, True, 1, **ski)) == 'fine'


def test_paragliding_weather():
    locale = {'route_description': 'from the summit', 'timing': '1h', 'weather': 'wind'}
    assert quality_v2(outing(['paragliding'], locale, track=True)) == 'medium'
    assert quality_v2(outing(['paragliding'], locale, track=True, images=1)) == 'fine'


def test_best_of_the_activities():
    locale = {
        'route_description': 'route',
        'description': 'equipment, rock',
        'timing': '5h',
        'weather': 'sunny',
    }
    assert quality_v2(outing(['mountain_climbing'], locale, images=1)) == 'medium'
    activities = ['mountain_climbing', 'rock_climbing']
    assert quality_v2(outing(activities, locale, images=1)) == 'fine'


def test_conditions_levels():
    levels = (
        '[{"level_snow_height_soft": "20", "level_place": "", "level_comment": ""}]'
    )
    ski = outing(['skitouring'], {'conditions_levels': levels, 'description': 'x'})
    # description 0.5 + the levels 1
    assert quality_v2(ski) == 'draft'
    assert (
        quality_v2(outing(['skitouring'], {'conditions_levels': 'not json'})) == 'empty'
    )


def test_recomputed_quality():
    detailed = outing(
        ['rock_climbing'],
        {'route_description': 'approach', 'description': 'rock'},
        images=1,
    )
    # computed by the old rules: recomputed
    assert recomputed_quality('draft', [detailed]) == 'medium'
    # already the latest
    assert recomputed_quality('medium', [detailed]) is None
    # chosen by its author: kept
    assert recomputed_quality('fine', [detailed]) is None
    assert recomputed_quality('great', [detailed]) is None
    # no locale
    assert recomputed_quality('draft', []) is None


def test_recomputed_quality_in_the_computed_locales():
    # the quality was computed in the French locale (draft by the old rules)
    fr = outing(['rock_climbing'], {'description': 'rock'})
    # the English one is empty
    en = outing(['rock_climbing'], {})
    assert quality_v1(fr) == 'draft'
    assert recomputed_quality('draft', [en, fr]) is None
    fr_timing = outing(['rock_climbing'], {'description': 'rock', 'timing': '5h'})
    # 1.5 (draft) with both rules
    assert recomputed_quality('draft', [en, fr_timing]) is None
    fr_detailed = outing(
        ['rock_climbing'], {'description': 'rock', 'route_description': 'r'}, images=1
    )
    assert recomputed_quality('draft', [en, fr_detailed]) == 'medium'
