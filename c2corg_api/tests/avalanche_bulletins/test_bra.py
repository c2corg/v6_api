import os

import pytest

from c2corg_api.avalanche_bulletins.bra import InvalidBulletin, bra_to_caaml

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def bulletin(massif):
    with open(os.path.join(FIXTURES, f'BRA_{massif}.xml'), 'rb') as f:
        bulletins = bra_to_caaml(f.read())['bulletins']
    return bulletins[0] if bulletins else None


def test_two_elevation_bands_all_day():
    # Mont-Blanc: 3 below 2200 m, 4 above
    b = bulletin(3)
    assert b['bulletinID'] == 'FR-03_2026-11-21T16:00:00+01:00'
    assert b['regions'] == [{'regionID': 'FR-03', 'name': 'Mont-Blanc'}]
    assert b['validTime'] == {
        'startTime': '2026-11-21T16:00:00+01:00',
        'endTime': '2026-11-22T18:00:00+01:00',
    }
    assert b['dangerRatings'] == [
        {
            'mainValue': 'considerable',
            'validTimePeriod': 'all_day',
            'elevation': {'upperBound': '2200'},
        },
        {
            'mainValue': 'high',
            'validTimePeriod': 'all_day',
            'elevation': {'lowerBound': '2200'},
        },
    ]
    assert b['avalancheProblems'] == [
        {'problemType': 'new_snow'},
        {'problemType': 'wet_snow'},
    ]
    assert b['tendency'][0]['tendencyType'] == 'steady'
    # the day it is valid for: the date of its URL once the bulletins are kept
    assert b['customData']['ALBINA'] == {'mainDate': '2026-11-22'}
    meteofrance = b['customData']['MeteoFrance']
    assert meteofrance['maxDangerRating'] == 'high'
    assert meteofrance['elevationThreshold'] == 2200
    assert meteofrance['avalancheProneLocation'] == {
        'aspects': ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    }
    assert meteofrance['snowCover']['levels'][-1] == {
        'elevation': 2500,
        'north': 130,
        'south': 120,
    }
    assert meteofrance['newSnow']['elevation'] == 1800
    forecast = meteofrance['weather']['forecasts'][0]
    # the French wind directions, in English
    assert forecast['wind'] == [
        {'direction': 'S', 'speed': 30},
        {'direction': 'SW', 'speed': 80},
    ]
    assert forecast['time'] == '2026-11-22T06:00:00+01:00'
    assert len(meteofrance['history']['maxDangerRatings']) == 7


def test_the_danger_changes_in_the_afternoon():
    # Haute-Tarentaise: above 2500 m, 3 in the morning and 4 in the afternoon
    ratings = [
        (r['validTimePeriod'], r['elevation'], r['mainValue'])
        for r in bulletin(6)['dangerRatings']
    ]
    assert ratings == [
        ('earlier', {'upperBound': '2500'}, 'considerable'),
        ('earlier', {'lowerBound': '2500'}, 'considerable'),
        ('later', {'upperBound': '2500'}, 'considerable'),
        ('later', {'lowerBound': '2500'}, 'high'),
    ]


def test_one_danger_for_all_elevations():
    # Chartreuse: 1, no marked problem, no dangerous aspect, 2 the day after
    b = bulletin(7)
    assert b['dangerRatings'] == [{'mainValue': 'low', 'validTimePeriod': 'all_day'}]
    assert b['avalancheProblems'] == [{'problemType': 'no_distinct_avalanche_problem'}]
    assert 'avalancheProneLocation' not in b['customData']['MeteoFrance']
    tendency = b['tendency'][0]
    assert tendency['tendencyType'] == 'increasing'
    assert tendency['customData'] == {'MeteoFrance': {'maxDangerRating': 'moderate'}}
    assert tendency['validTime']['startTime'] == '2026-11-23T00:00:00+01:00'


def test_the_sections_of_the_texts_on_their_own_lines():
    comment = bulletin(3)['avalancheActivity']['comment']
    assert comment.startswith('Départs spontanés :\n• Au-dessus de 2200 m :')
    assert '\nDéclenchements provoqués :\n• ' in comment
    assert '  ' not in comment


def test_no_bulletin():
    # Andorra: a message pointing to the service of Andorra
    assert bulletin(71) is None


def test_invalid_xml():
    with pytest.raises(InvalidBulletin):
        bra_to_caaml(b'<BULLETINS_NEIGE_AVALANCHE')
    # entities are refused (billion laughs and the like)
    with pytest.raises(InvalidBulletin):
        bra_to_caaml(b'<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
