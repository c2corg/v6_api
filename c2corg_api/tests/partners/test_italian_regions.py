"""The Italian region tables of on-ice.it and gulliver.it (`partners/regions`)."""

import json

import pytest

from c2corg_api.partners import region_map
from c2corg_api.partners.sources import onice

ITALY = 14270
AOSTA = 280072
TORINO = 280066
CUNEO = 280000
BOLZANO = 279985
TRENTO = 280068
SONDRIO = 280062


def data(source):
    path = region_map.DIRECTORY / f'{source}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def regions(source):
    return {k: v for k, v in data(source)['regions'].items() if v['country'] == 'IT'}


def test_every_onice_region_is_in_the_table():
    for name in onice.ITALIAN_REGIONS:
        areas = region_map.lookup('onice', name)
        assert areas is not None, name
        assert areas.country == 'IT'
        assert areas.area_ids
    for name, country in onice.COUNTRIES.items():
        areas = region_map.lookup('onice', name)
        assert (areas.country, areas.area_ids) == (country, ())
    assert region_map.lookup('onice', 'Altro') is None


@pytest.mark.parametrize('source', ['onice', 'gulliver'])
def test_a_province_is_in_one_region(source):
    table = data(source)
    assert table['countries'] == {'IT': ITALY}
    names = [n for n in table['regions'] if len(n) > 2]
    ids = [i for n in names for i in table['regions'][n]['area_ids']]
    assert len(ids) == len(set(ids)) == 110
    assert all(isinstance(i, int) and i > 0 for i in ids)
    assert {'checked', 'site', 'area_ids', 'range_ids'} <= set(table['coverage'])


def test_both_sources_agree_on_the_regions():
    gulliver = {n: v for n, v in regions('gulliver').items() if len(n) > 2}
    assert len(gulliver) == 20
    for name, entry in gulliver.items():
        assert region_map.lookup('onice', name).area_ids == tuple(entry['area_ids'])


def test_each_province_code_is_one_province_of_its_region():
    table = regions('gulliver')
    codes = {n: v for n, v in table.items() if len(n) == 2}
    # 110 provinces of the c2c areas, plus Sud Sardegna
    assert len(codes) == 111
    for code, entry in codes.items():
        if code == 'SU':
            continue
        assert len(entry['area_ids']) == 1, code
    provinces = {v['area_ids'][0] for c, v in codes.items() if c != 'SU'}
    in_regions = {i for n, v in table.items() if len(n) > 2 for i in v['area_ids']}
    assert provinces == in_regions


@pytest.mark.parametrize(
    ('text', 'first'),
    [
        ("Valle d'Aosta", AOSTA),
        ('Valle d’Aosta', AOSTA),
        ('Trentino Alto Adige', BOLZANO),
        ('Trentino-Alto Adige', BOLZANO),
        ('LOMBARDIA', SONDRIO),
        ('Piemonte', TORINO),
    ],
)
def test_onice_region_texts(text, first):
    assert region_map.lookup('onice', text).area_ids[0] == first


@pytest.mark.parametrize(
    ('text', 'area_ids', 'country'),
    [
        ("Valle d'Aosta - AO", (AOSTA,), 'IT'),
        ('Piemonte - CN', (CUNEO,), 'IT'),
        ('Trentino-Alto Adige - TN', (TRENTO,), 'IT'),
        ('Trentino-Alto Adige - BZ', (BOLZANO,), 'IT'),
        # an unknown district: the region
        ('Piemonte - XX', 'Piemonte', 'IT'),
        ('Piemonte', 'Piemonte', 'IT'),
        ('TO', (TORINO,), 'IT'),
    ],
)
def test_gulliver_region_and_district(text, area_ids, country):
    areas = region_map.lookup('gulliver', text)
    if isinstance(area_ids, str):
        area_ids = region_map.lookup('onice', area_ids).area_ids
    assert (areas.area_ids, areas.country) == (area_ids, country)


@pytest.mark.parametrize(
    'text',
    [
        'Valais (CH) - Brig',
        "Provence-Alpes-Côte d'Azur (FR) - Hautes-Alpes",
        'Isole Canarie (ES) - La Palma',
        '',
        None,
    ],
)
def test_gulliver_foreign_regions_are_not_in_the_table(text):
    assert region_map.lookup('gulliver', text) is None
