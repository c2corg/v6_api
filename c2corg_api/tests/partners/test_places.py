"""The folding of summit names (`partners.places`) and the country table."""

import pytest

from c2corg_api.partners import places, region_map


@pytest.mark.parametrize(
    ('a', 'b'),
    [
        # accents, umlauts and their spelled-out forms, case
        ('Piz Palü', 'PIZ PALU'),
        ('Mönch', 'Moench'),
        ('Hochkönig', 'Hochkoenig'),
        ('Großer Priel', 'Grosser Priel'),
        ('Écrins', 'ecrins'),
        ('Grand Pic de la Lauzière', 'Grand pic de la Lauziere'),
        ('Kasprowy Wierch', 'Kaśprowy Wiérch'),
        # German suffixes written apart or joined
        ('Riedberger Horn', 'Riedbergerhorn'),
        ('Pyramiden Spitze', 'Pyramidenspitze'),
        ('Gross Litzner Spitz', 'Gross Litznerspitz'),
        # punctuation, brackets, an elevation in the name
        ('Pointe de Tcholeire 2440m', 'Pointe de Tcholeire'),
        ('Hochkönig 2941 m', 'Hochkönig'),
        ('Le Dôme (Les Diablerets)', 'Le Dôme'),
        ("Pointe d'Arpette", 'Pointe d Arpette'),
        ('Sigriswiler-Rothorn', 'Sigriswiler Rothorn'),
    ],
)
def test_same_full_key(a, b):
    assert places.full_key(a) == places.full_key(b)


@pytest.mark.parametrize(
    ('name', 'short'),
    [
        ('Pointe de la Galise', 'galise'),
        ('Piz Corvatsch', 'corvatsch'),
        ('Pizzo di Vogorno', 'vogorno'),
        ('Monte Rosa', 'rosa'),
        ('Gr. Priel', 'priel'),
        ('Großer Priel', 'priel'),
        ('Hintere Goinger Halt', 'goinger halt'),
        ("Aiguille d'Argentière", 'argentiere'),
        ('Tête de la Maye', 'maye'),
        # nothing generic, or nothing left: the full key
        ('Col de la Forclette', 'col de la forclette'),
        ('Piz', 'piz'),
        ('La Tête', 'tete'),  # the last word stays
    ],
)
def test_short_key_drops_generic_words(name, short):
    assert places.keys(name)[1] == short


def test_different_names_stay_apart():
    assert places.full_key('Grand Combin') != places.full_key('Combin')
    assert places.full_key('Pointe de la Galise') != places.full_key('Galise')
    assert places.full_key('Mont Blanc') != places.full_key('Mont Blanc du Tacul')


def test_empty_names():
    assert places.keys(None) == ('', '')
    assert places.keys('') == ('', '')
    assert places.keys(' - ') == ('', '')
    assert places.keys('2440 m') == ('', '')


def test_country_areas():
    assert region_map.country_area('CH') == 14067
    assert region_map.country_area(' at ') == 14257
    assert region_map.country_area('LI') == 14381
    assert region_map.country_area('XX') is None
    assert region_map.country_area(None) is None
    assert region_map.country_area('') is None


def test_every_country_of_a_region_table_is_known():
    # the regions of skitourenportal name their country: it must be in the table
    for entry in region_map.load('skitourenportal').values():
        assert region_map.country_area(entry.country) is not None
