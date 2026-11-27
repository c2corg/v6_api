import datetime
import json
import shutil
from pathlib import Path

import pytest

from c2corg_api.partners import contract, htmlparse, normalise
from c2corg_api.partners.adapter import ParseError, SourceBlocked
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import TEXT_KINDS, FetchContext, HarvestedOuting
from c2corg_api.partners.sources import REGISTRY, onice
from c2corg_api.partners.sources.onice import OniceAdapter
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
LIST = 'http://www.on-ice.it/onice/onice_reports.php'
DETAIL = 'http://www.on-ice.it/onice/onice_view_report.php'
SINCE = datetime.date(2026, 11, 13)
NOW = datetime.datetime(2026, 11, 27, 8, 0, tzinfo=datetime.UTC)
# the outings of the period in the recording (2026-11-27, since 2026-11-13)
RECORDED = {
    '1-26069',
    '1-26070',
    '1-26071',
    '2-13777',
    '2-13778',
    '2-13779',
    '2-13780',
    '3-7321',
    '3-7322',
    '6-528',
    '6-529',
    '6-530',
}
EMAIL = 'mario.rossi@example.com'
# a detail page as the site writes it (ISO-8859-1, the e-mail of the author in
# an HTML comment, UTF-8 bytes in a field); invented content
RAW_DETAIL = (
    '<html><body><table><tr>'
    '<td class="report-title">&nbsp;Pizzo Test, 21/11/2026</td>'
    '<td><div class="fb-like"></div></td></tr></table>'
    '<table>'
    '<tr><td class="reportrowlabel">Onicer</td>\n'
    f'<!-- <span class="email">{EMAIL}</span> -->\n'
    '<td class="reportrow">&nbsp;<a class="reportlink" '
    'href="./profile.php?mode=viewprofile&u=12">Mario</a></td></tr>'
    '<tr><td class="reportrowlabel">Partenza</td>'
    '<td class="reportrow">&nbsp;Cusi\xe8 &nbsp;(1709 m)</td></tr>'
    '<tr><td class="reportrowlabel">Quota arrivo</td>'
    '<td class="reportrow">&nbsp;3402 m</td></tr>'
    '<tr><td class="reportrowlabel">Difficolt&agrave;</td>'
    '<td class="reportrow">&nbsp;F+ ( pendenza 30\xc2\xb0 )</td></tr>'
    '<tr><td class="reportrowlabel">Esposizione in salita</td>'
    '<td class="reportrow">&nbsp;Sud-Ovest</td></tr>'
    '<tr><td class="reportrowlabel">Itinerari collegati</td>'
    '<td class="reportrow">&nbsp;nessuno</td></tr>'
    '<tr><td class="reportrowlabel">Neve prevalente</td>'
    '<td class="reportrow">&nbsp;Farinosa</td></tr>'
    '<tr><td class="reportrowlabel">Altra neve</td>'
    '<td class="reportrow">&nbsp;Crostosa</td></tr>'
    '<tr><td class="reportrowlabel">Rischio valanghe</td>'
    '<td class="reportrow">&nbsp;2 - Moderato</td></tr>'
    '<tr><td class="reportrowlabel">Rifugio di appoggio</td>'
    '<td class="reportrow">&nbsp;nessuno</td></tr>'
    '<tr><td class="reportrowlabel">Commento</td>'
    '<td class="reportcommento">Bella gita.<br>Scrivetemi: '
    f'{EMAIL}<br><br><iframe src="https://x"></iframe>Ciao</td></tr>'
    '<tr><td class="reportrowlabel">Immagini</td>'
    '<td class="reportrow"><img src="./upload/x.jpg"></td></tr>'
    '</table></body></html>\n<br><center>after the end</center>'
).encode('latin-1')
FATAL = (
    b'<br />\n<b>Fatal error</b>:  Call to a member function getIdItinerario() on a'
    b' non-object in <b>/www/onice_view_report.php</b> on line <b>28</b><br />\n'
)


class Spy:
    """Wraps a transport and records the requests."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    @property
    def request_count(self):
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None):
        self.calls.append((url, {k: str(v) for k, v in (params or {}).items()}))
        return self.inner.get(url, params=params, headers=headers)

    def lists(self):
        return [p.get('start', '0') for u, p in self.calls if u == LIST]

    def details(self):
        return [f'{p["type"]}-{p["id"]}' for u, p in self.calls if u == DETAIL]


class Canned:
    """A transport that answers the same response to everything."""

    request_count = 0

    def __init__(self, status=200, body=b'', content_type='text/html'):
        self.response = HttpResponse(
            status, {'Content-Type': content_type}, body, 'http://x'
        )

    def get(self, url, *, params=None, headers=None):
        return self.response


def run(transport=None, lookups=None, since=SINCE, cursor=None):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    spy = Spy(
        transport
        if transport is not None
        else FixtureTransport(FIXTURES, 'onice', OniceAdapter.rate)
    )
    ctx = FetchContext(
        since=since,
        now=NOW,
        cursor=cursor,
        transport=spy,
        lookups=lookups,
        secrets={},
    )
    return OniceAdapter().fetch(ctx), spy, lookups


def by_id(result):
    return {o.external_id: o for o in result.outings}


def fixture_copy(tmp_path, **replacements):
    """A copy of the fixtures; `name=(old, new)` edits the text of a file."""
    target = tmp_path / 'onice'
    shutil.copytree(FIXTURES / 'onice', target)
    for name, (old, new) in replacements.items():
        path = target / name
        text = path.read_text(encoding='utf-8')
        assert old in text, (name, old)
        path.write_text(text.replace(old, new, 1), encoding='utf-8')
    return tmp_path


def run_copy(tmp_path, **kwargs):
    return run(FixtureTransport(tmp_path, 'onice'), **kwargs)


def set_entry(tmp_path, file, **changes):
    """Edit the manifest entry of a file in a fixture copy."""
    path = tmp_path / 'onice' / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for entry in manifest['entries']:
        if entry['file'] == file:
            entry.update(changes)
    path.write_text(json.dumps(manifest), encoding='utf-8')


# -- the source --------------------------------------------------------------


def test_registered_and_credited():
    assert REGISTRY['onice'] is OniceAdapter
    assert OniceAdapter.name == 'onice'
    assert OniceAdapter.site_name == 'on-ice.it'
    assert OniceAdapter.site_url == 'http://www.on-ice.it/onice/'
    assert OniceAdapter.required_secrets == ()
    assert OniceAdapter.rate.min_interval_s >= 2
    assert OniceAdapter.rate.max_requests_per_run == (
        onice.MAX_PAGES + onice.MAX_DETAIL_FETCHES
    )


def test_fixtures_are_recorded_not_synthetic():
    manifest = json.loads((FIXTURES / 'onice' / 'manifest.json').read_text())
    assert manifest['synthetic'] is False
    files = {e['file'] for e in manifest['entries']}
    assert 'onice_reports_type0.html' in files
    assert 'onice_reports_start60_type0_u0.html' in files
    assert len(files) == 2 + len(RECORDED)


def test_every_site_type_is_mapped():
    for code in onice.TYPES.values():
        assert normalise.map_activity('onice', code), code


# -- a run on the recording ----------------------------------------------------


def test_run_on_the_recording():
    result, spy, lookups = run()
    assert set(by_id(result)) == RECORDED
    assert result.item_errors == 0
    assert result.cursor is None
    # page 1, then page 2 (the list is new to us), then one detail per outing
    assert spy.lists() == ['0', '60']
    assert sorted(spy.details()) == sorted(RECORDED)
    assert all(lookups.get(f'report:{i}') for i in RECORDED)
    assert set(result.skipped) == {'too_old'}


def test_ski_outing_with_its_detail():
    outing = by_id(run()[0])['1-26071']
    assert outing == HarvestedOuting(
        source='onice',
        external_id='1-26071',
        url=f'{DETAIL}?type=1&id=26071',
        title='Aiguille de lesache o des sasses(quasi)',
        date=datetime.date(2026, 11, 21),
        activities=('skitouring',),
        author=outing.author,
        author_url=outing.author_url,
        lang='it',
        region="Valle d'Aosta",
        source_activity='scialpinismo',
        ski_rating_min='2.1',
        ski_rating_max='3.3',
        rating_raw='BS',
        rating_system='blachere',
        steep=False,
        elevation_max=2865,
        height_diff_up=1150,
        orientations=('E',),
        texts=outing.texts,
        summit_name='Aiguille de lesache o des sasses',
        country='IT',
    )
    assert htmlparse.PSEUDONYM.fullmatch(outing.author)
    assert outing.author_url == f'http://www.on-ice.it/onice/{outing.author}.php'
    # the texts are there, redacted in the recording
    assert set(outing.texts) == {'narrative', 'conditions', 'snow', 'access'}
    assert contract.REDACTED.fullmatch(outing.texts['narrative'])
    assert outing.texts['snow'].startswith('Neve prevalente: [text ')


def test_outings_of_other_types():
    outings = by_id(run()[0])
    hiking, rock, mtb = outings['2-13778'], outings['3-7322'], outings['6-530']
    assert hiking.activities == ('hiking',)
    assert (hiking.summit_name, hiking.elevation_max) == ('Monte Guglielmo', 1953)
    assert hiking.rating_raw == 'E'
    assert hiking.ski_rating_min is None
    assert rock.activities == ('rock_climbing',)
    assert rock.rating_raw == 'TD- / 6b ( 6a obbl. )'
    assert rock.orientations == ('S',)
    assert mtb.activities == ('mountain_biking',)
    assert mtb.elevation_max == 2500  # 'Quota massima'
    assert outings['1-26069'].country == 'CH'  # 'Svizzera'
    for outing in outings.values():
        assert outing.lat is None and outing.lon is None
        assert outing.geom_quality == 'none'
        assert outing.gpx_url is None
        assert set(outing.texts or {}) <= set(TEXT_KINDS)


def test_cached_details_are_never_asked_again():
    _, _, lookups = run()
    result, spy, _ = run(lookups=lookups)
    assert set(by_id(result)) == RECORDED
    # the newest reports are known: no page 2, no detail page
    assert spy.lists() == ['0']
    assert spy.details() == []
    assert by_id(result)['1-26071'].elevation_max == 2865


def test_the_detail_cap(monkeypatch):
    monkeypatch.setattr(onice, 'MAX_DETAIL_FETCHES', 3)
    result, spy, lookups = run()
    assert len(spy.details()) == 3
    assert result.skipped['detail_deferred'] == len(RECORDED) - 3
    # over the cap: the hints of the list
    deferred = [o for o in result.outings if o.external_id not in spy.details()]
    assert all(o.texts is None and o.rating_raw is None for o in deferred)
    canzenagol = by_id(result)['2-13779']
    assert (canzenagol.summit_name, canzenagol.elevation_max) == ('Canzenagol', 2457)
    # the next run goes on
    result, spy, _ = run(lookups=lookups)
    assert len(spy.details()) == 3
    assert result.skipped['detail_deferred'] == len(RECORDED) - 6


def test_old_outings_are_skipped():
    result, spy, _ = run(since=datetime.date(2026, 11, 22))
    assert set(by_id(result)) == {'3-7322'}
    assert spy.details() == ['3-7322']


def test_fatal_error_page_is_a_gone_report(tmp_path):
    fixture_copy(tmp_path)
    (tmp_path / 'onice' / 'onice_view_report_id26071_type1.html').write_bytes(FATAL)
    result, _, lookups = run_copy(tmp_path)
    outing = by_id(result)['1-26071']
    assert result.skipped['detail_gone'] == 1
    assert outing.elevation_max is None and outing.texts is None
    assert lookups.get('report:1-26071') == {'gone': True}  # never asked again


def test_failing_detail_page_is_not_cached(tmp_path):
    fixture_copy(tmp_path)
    set_entry(tmp_path, 'onice_view_report_id26071_type1.html', status=503)
    result, _, lookups = run_copy(tmp_path)
    assert '1-26071' in by_id(result)
    assert result.skipped['lookup_failed'] == 1
    assert lookups.get('report:1-26071') is None


def test_blocked_detail_page_stops_the_run(tmp_path):
    fixture_copy(tmp_path)
    set_entry(tmp_path, 'onice_view_report_id26071_type1.html', status=403)
    with pytest.raises(SourceBlocked):
        run_copy(tmp_path)


def test_unparsable_row_is_an_item_error(tmp_path):
    fixture_copy(
        tmp_path,
        **{'onice_reports_type0.html': ('21/11/2026', '31/02/2026')},
    )
    result, _, _ = run_copy(tmp_path)
    assert result.item_errors == 1
    assert len(result.outings) == len(RECORDED) - 1


def test_unmapped_type_is_counted(tmp_path):
    fixture_copy(
        tmp_path,
        **{'onice_reports_type0.html': ('type=6&amp;id=530', 'type=5&amp;id=530')},
    )
    result, _, _ = run_copy(tmp_path)
    assert result.skipped['unmapped_activity:5'] == 1
    assert '6-530' not in by_id(result)


def test_ice_fall_of_the_ice_and_mixed_type(tmp_path):
    fixture_copy(
        tmp_path,
        **{
            'onice_reports_type0.html': (
                'type=6&amp;id=530">\n      LATEMAR - OBEREGGEN DOLOMITI 2500mt',
                'type=4&amp;id=530">\n      Cascata del Pisgana',
            )
        },
    )
    outing = by_id(run_copy(tmp_path)[0])['4-530']
    assert outing.activities == ('ice_climbing',)
    assert outing.source_activity == 'ghiaccio_misto'


def test_page_without_a_list_is_a_parse_error():
    with pytest.raises(ParseError, match='no list'):
        run(Canned(body=b'<html><body>nothing</body></html>'))


def test_http_error_on_the_list_is_a_parse_error():
    with pytest.raises(ParseError, match='HTTP 404'):
        run(Canned(status=404))


# -- parsing -----------------------------------------------------------------


def test_decode_and_mojibake():
    assert onice.decode('Cusiè'.encode('latin-1')) == 'Cusiè'
    assert onice.decode('Cusiè'.encode()) == 'Cusiè'
    assert onice.fix_mojibake('pendenza 30Â°') == 'pendenza 30°'
    assert onice.fix_mojibake('Cusiè') == 'Cusiè'
    assert onice.fix_mojibake('Ã and è') == 'Ã and è'  # not UTF-8: as is


@pytest.mark.parametrize(
    ('title', 'hint'),
    [
        ('Mont Miravidi, dal Lago Verney', ('Mont Miravidi', None)),
        ('Monte Guglielmo 1953 m, traversata', ('Monte Guglielmo', 1953)),
        ('Canzenagol m 2457 - cresta W', ('Canzenagol', 2457)),
        ('Adula 3402m', ('Adula', 3402)),
        (
            'Passo della Rossola e dintorni ( VIDEO )',
            ('Passo della Rossola e dintorni', None),
        ),
        ('2026', (None, None)),
    ],
)
def test_summit_hint(title, hint):
    assert onice.summit_hint(title) == hint


def test_orientations_and_countries():
    assert onice.orientations(['Sud-Est', 'Nord', 'Varia', 'Sud-Est']) == ('SE', 'N')
    assert onice.orientations(['Nord-Ovest']) == ('NW',)
    assert onice.country_of("Valle d'Aosta") == 'IT'
    assert onice.country_of('Svizzera') == 'CH'
    assert onice.country_of('Francia') == 'FR'
    assert onice.country_of('Altro') is None


def test_extract_detail_of_a_raw_page():
    detail = onice.extract_detail(onice.decode(RAW_DETAIL))
    assert detail['elevation'] == 3402
    assert detail['rating'] == 'F+ ( pendenza 30° )'
    assert detail['orientations'] == ['SW']
    assert detail['texts'] == {
        'access': 'Partenza: Cusiè (1709 m)',
        'snow': 'Neve prevalente: Farinosa\nAltra neve: Crostosa',
        'conditions': 'Rischio valanghe: 2 - Moderato',
        'narrative': 'Bella gita.\nScrivetemi:\n\nCiao',
    }
    assert EMAIL not in json.dumps(detail)
    assert onice.extract_detail(FATAL.decode()) == {'gone': True}


def test_extract_texts():
    assert onice.extract_texts({}) is None
    assert onice.extract_texts(
        {
            'Commento': 'Bella.\nScrivi a a.b@c.it',
            'Condizioni': 'Ottime',
            'Valutazione itinerario': 'Buono',
            'Rifugio di appoggio': 'nessuno',
            'Attrezzatura consigliata': 'piccozza',
            'Report visto': '12 volte',
        }
    ) == {
        'narrative': 'Bella.\nScrivi a',
        'conditions': 'Condizioni: Ottime\nValutazione itinerario: Buono',
        'equipment': 'Attrezzatura consigliata: piccozza',
    }


# -- recording ---------------------------------------------------------------


def test_endpoint_names_of_the_site():
    assert contract.endpoint_of(LIST, 'onice') == 'onice_reports'
    assert contract.endpoint_of(DETAIL, 'onice') == 'onice_view_report'


def test_trim_keeps_the_fields_drops_the_texts_and_the_email():
    body = contract.trim_body('onice', DETAIL, RAW_DETAIL)
    text = body.decode('utf-8')
    assert EMAIL not in text and '@' not in text
    assert 'Fatal' not in text and 'after the end' not in text
    assert 'Bella gita' not in text and 'Farinosa' not in text
    assert 'Mario' not in text  # the author row is not read
    assert '<img' not in text and '<iframe' not in text
    assert 'Cusiè' not in text  # a text: redacted
    detail = onice.extract_detail(onice.decode(body))
    assert detail['elevation'] == 3402
    assert detail['rating'] == 'F+ ( pendenza 30° )'  # decoded, not replaced
    assert detail['orientations'] == ['SW']
    assert all(contract.REDACTED.search(value) for value in detail['texts'].values())
    # idempotent: the committed fixtures are trimmed already
    assert contract.trim_body('onice', DETAIL, body) == body


def test_captured_shapes_of_a_run_match_the_fixtures():
    adapter = REGISTRY['onice']()
    transport = contract.CapturingTransport(
        FixtureTransport(FIXTURES, 'onice', OniceAdapter.rate)
    )
    contract.run_adapter(adapter, transport, {}, SINCE, NOW)
    actual = contract.captured_shapes('onice', transport.responses)
    expected = contract.fixture_shapes(FIXTURES / 'onice')
    report = contract.compare(adapter, expected, actual)
    assert not report.breaking, report.problems
