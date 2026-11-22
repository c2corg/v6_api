from datetime import datetime

import pytest

from c2corg_api.avalanche_bulletins.bra import PARIS
from c2corg_api.avalanche_bulletins.meteofrance import (
    EXPIRATION,
    EXPIRATION_AT_PUBLICATION,
    expiration,
    massif_of,
)


@pytest.mark.parametrize(
    ('region_id', 'massif'),
    [('FR-03', 3), ('FR-74', 74), ('FR-71', None), ('FR-99', None), ('CH-42', None)],
)
def test_massif_of(region_id, massif):
    assert massif_of(region_id) == massif


@pytest.mark.parametrize(
    ('hour', 'minute', 'seconds'),
    [
        (15, 29, EXPIRATION),
        (15, 30, EXPIRATION_AT_PUBLICATION),
        (18, 30, EXPIRATION_AT_PUBLICATION),
        (18, 31, EXPIRATION),
    ],
)
def test_expiration_shorter_around_the_publication(hour, minute, seconds):
    assert expiration(datetime(2026, 11, 21, hour, minute, tzinfo=PARIS)) == seconds
