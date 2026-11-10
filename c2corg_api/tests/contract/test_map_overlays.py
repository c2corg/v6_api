import pytest

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.search.__init__ import reset_search_index

OUTINGS_HEATMAP = ('GET', '/outings/map/heatmap')
OUTINGS_TRACKS = ('GET', '/outings/map/tracks')
ROUTES_HEATMAP = ('GET', '/routes/map/heatmap')
ROUTES_TRACKS = ('GET', '/routes/map/tracks')

# the whole world (EPSG:3857), a box with no outing nor route
WORLD = '-20000000,-20000000,20000000,20000000'
EMPTY = '0,0,10,10'


@pytest.fixture
def searchable(session, documents):
    """Index the documents created through the API."""
    reset_search_index(session)


class TestMapOverlays:
    @contract(OUTINGS_HEATMAP, ROUTES_HEATMAP)
    def test_heatmap(self, browser, searchable):
        for kind in ('outings', 'routes'):
            response = browser.get(f'/{kind}/map/heatmap?bbox={WORLD}&zoom=3')
            check_snapshot(f'{kind}_map_heatmap', response)
            assert response.json['buckets']

    @contract(OUTINGS_TRACKS, ROUTES_TRACKS)
    def test_tracks(self, browser, searchable):
        for kind in ('outings', 'routes'):
            response = browser.get(f'/{kind}/map/tracks?bbox={EMPTY}')
            check_snapshot(f'{kind}_map_tracks', response)
            assert response.json == {'documents': [], 'truncated': False}

    @contract(OUTINGS_HEATMAP, ROUTES_HEATMAP, OUTINGS_TRACKS, ROUTES_TRACKS)
    def test_missing_box(self, browser):
        for kind in ('outings', 'routes'):
            for path in ('heatmap?zoom=3', 'tracks'):
                response = browser.get(f'/{kind}/map/{path}', status=400)
                check_snapshot(f'{kind}_map_{path.split("?")[0]}_no_bbox', response)

    @contract(OUTINGS_HEATMAP, ROUTES_HEATMAP, OUTINGS_TRACKS, ROUTES_TRACKS)
    def test_turned_off(self, browser, monkeypatch):
        # TRACKS_OVERLAY_ENABLED=false: a 503 whatever the request, before the
        # servers are asked anything
        monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'false')
        for kind in ('outings', 'routes'):
            for path in ('heatmap', 'tracks'):
                response = browser.get(f'/{kind}/map/{path}', status=503)
                check_snapshot(f'{kind}_map_{path}_turned_off', response)
