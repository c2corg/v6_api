import json
import os
from datetime import datetime

import pytest

from c2corg_api.avalanche_bulletins.caaml import (
    SERVICES,
    _checked,
    _normalized,
    service_of,
)
from c2corg_api.avalanche_bulletins.cache import (
    CET,
    EXPIRATION,
    EXPIRATION_AT_PUBLICATION,
    UpstreamError,
    expiration,
    main_date,
)
from c2corg_api.avalanche_bulletins.meteofrance import massif_of
from c2corg_api.tests.avalanche_bulletins.test_bra import FIXTURES


def caaml(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


@pytest.mark.parametrize(
    ('region_id', 'massif'),
    [('FR-03', 3), ('FR-74', 74), ('FR-71', None), ('FR-99', None), ('CH-42', None)],
)
def test_massif_of(region_id, massif):
    assert massif_of(region_id) == massif


@pytest.mark.parametrize(
    ('region_id', 'service'),
    [
        ('CH-4231', 'CH'),
        ('CH', 'CH'),
        ('IT-32-BZ-01', 'IT-32-BZ'),
        ('IT-32-TN', 'IT-32-TN'),
        ('AT-07-14-01', 'AT-07'),
        ('SI-1', 'SI'),
        ('IT-3', None),
        ('CHX-1', None),
        ('FR-03', None),
    ],
)
def test_service_of(region_id, service):
    assert service_of(region_id) == service


def test_language_asked_else_english():
    assert SERVICES['CH'].lang_for('fr') == 'fr'
    assert SERVICES['SI'].lang_for('fr') == 'en'
    assert SERVICES['SI'].lang_for(None) == 'en'


@pytest.mark.parametrize(
    ('hour', 'minute', 'seconds'),
    [
        (7, 29, EXPIRATION),
        (7, 30, EXPIRATION_AT_PUBLICATION),
        (10, 1, EXPIRATION),
        (15, 30, EXPIRATION_AT_PUBLICATION),
        (18, 30, EXPIRATION_AT_PUBLICATION),
        (18, 31, EXPIRATION),
    ],
)
def test_expiration_shorter_around_the_publications(hour, minute, seconds):
    assert expiration(datetime(2026, 11, 21, hour, minute, tzinfo=CET)) == seconds


@pytest.mark.parametrize(
    ('end', 'day'),
    [
        # SLF, until 17:00 (updated at 08:00)
        ('2026-11-22T16:00:00Z', '2026-11-22'),
        # AINEVA, until midnight
        ('2026-11-22T23:00:00Z', '2026-11-22'),
        # Météo-France, until 18:00
        ('2026-11-22T18:00:00+01:00', '2026-11-22'),
        # without offset: in local time
        ('2026-11-23T00:00:00', '2026-11-22'),
    ],
)
def test_main_date_is_the_day_of_validity(end, day):
    assert main_date({'startTime': '2026-11-21T16:00:00Z', 'endTime': end}) == day


def test_provider_and_day_added_when_missing():
    service = SERVICES['CH']
    [slf, _] = [_normalized(b, service) for b in caaml('CH_fr.json')['bulletins']]
    assert slf['source']['provider'] == {
        'name': 'SLF',
        'website': 'https://www.slf.ch',
    }
    assert slf['customData']['ALBINA'] == {'mainDate': '2026-11-22'}
    # kept when given
    [aineva, *_] = caaml('IT-23_fr.json')['bulletins']
    given = aineva['customData']['ALBINA']['mainDate']
    assert _normalized(aineva, SERVICES['IT-23'])['customData']['ALBINA'] == {
        'mainDate': given
    }


@pytest.mark.parametrize(
    'data',
    [
        {},
        {'bulletins': [{'regions': [{'regionID': 'CH-1'}]}]},
        {'bulletins': [{'regions': [{}], 'validTime': {'endTime': '2026'}}]},
        {'bulletins': [{'regions': [{'regionID': 'CH-1'}], 'validTime': {}}]},
    ],
)
def test_not_caaml(data):
    with pytest.raises(UpstreamError):
        _checked(data, 'https://example.org')
