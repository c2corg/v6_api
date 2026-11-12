from pyproj import Transformer

from c2corg_api.tests import encode_polyline
from c2corg_api.tests.contract import check_snapshot, contract

SUGGEST = ('GET', '/routes/suggest')

# the route of the documents fixture, at 635956 5723604 (EPSG:3857)
TO_4326 = Transformer.from_crs('EPSG:3857', 'EPSG:4326', always_xy=True)
TRACK = encode_polyline(
    [TO_4326.transform(x, y) for x, y in ((635900, 5723500), (636000, 5723700))]
)


@contract(SUGGEST)
def test_suggest(browser, documents):
    response = browser.get('/routes/suggest', params={'track': TRACK, 'pl': 'en'})
    check_snapshot('routes_suggest', response)
    assert [d['document_id'] for d in response.json['documents']] == [
        documents.ids['routes']
    ]


@contract(SUGGEST)
def test_suggest_invalid(browser):
    response = browser.get('/routes/suggest', params={'track': '~'}, status=422)
    check_snapshot('routes_suggest_invalid', response)
