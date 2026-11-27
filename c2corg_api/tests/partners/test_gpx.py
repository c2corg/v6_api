"""The GPX reader: points only, hostile files refused."""

from pathlib import Path

import pytest

from c2corg_api.partners import gpx

TRACKS = Path(__file__).parent / 'fixtures' / 'gulliver_tracks'
NS = 'xmlns="http://www.topografix.com/GPX/1/1"'


def doc(body, head=''):
    return f'<?xml version="1.0"?>{head}<gpx version="1.1" {NS}>{body}</gpx>'.encode()


def segment(*points, tag='trkpt'):
    return ''.join(f'<{tag} lat="{lat}" lon="{lon}"/>' for lon, lat in points)


def test_synthetic_fixture_keeps_the_points_only():
    body = (TRACKS / 'AnelloBorgateMontecrestese.gpx').read_bytes()
    assert b'Synthetic Author' in body and b'<gpxtpx:hr>' in body
    track = gpx.parse(body)
    assert track.point_count == 60
    assert track.simplified is False
    (line,) = track.lines
    assert len(line) == 60
    assert line[0] == (8.325, 46.155, 600.0)
    wkt = gpx.wkt(track)
    assert wkt.startswith('MULTILINESTRING ((8.325 46.155, ')
    # nothing but numbers: no time, heart rate, name or author
    for word in ('Synthetic', '2000-01-01', 'hr', 'waypoint'):
        assert word not in wkt and word not in repr(track)


def test_tracks_segments_and_routes():
    body = doc(
        '<wpt lat="45" lon="7"><name>Home of someone</name></wpt>'
        f'<trk><trkseg>{segment((7, 45), (7.1, 45.1))}</trkseg>'
        f'<trkseg>{segment((7.2, 45.2), (7.3, 45.3), (7.4, 45.4))}</trkseg></trk>'
        f'<rte>{segment((8, 46), (8.1, 46.1), tag="rtept")}</rte>'
    )
    track = gpx.parse(body)
    assert [len(line) for line in track.lines] == [2, 3, 2]
    assert track.point_count == 7
    assert gpx.wkt(track) == (
        'MULTILINESTRING ((7.0 45.0, 7.1 45.1), (7.2 45.2, 7.3 45.3, 7.4 45.4), '
        '(8.0 46.0, 8.1 46.1))'
    )


def test_bad_points_are_skipped():
    body = doc(
        '<trk><trkseg>'
        '<trkpt lat="x" lon="7"/><trkpt lat="91" lon="7"/><trkpt lat="0" lon="0"/>'
        '<trkpt lat="nan" lon="7"/><trkpt lon="7"/>'
        f'{segment((7, 45), (7.1, 45.1))}'
        '<trkpt lat="45.2" lon="7.2"><ele>huge</ele></trkpt>'
        '</trkseg><trkseg>'
        f'{segment((7, 45))}'  # one point: no line
        '</trkseg></trk>'
    )
    track = gpx.parse(body)
    assert track.lines == (((7.0, 45.0, None), (7.1, 45.1, None), (7.2, 45.2, None)),)


def test_long_lines_are_simplified():
    points = [(7 + i * 1e-5, 45 + ((i % 7) - 3) * 1e-7) for i in range(5000)]
    track = gpx.parse(doc(f'<trk><trkseg>{segment(*points)}</trkseg></trk>'))
    assert track.simplified is True
    assert track.point_count == 5000
    assert 2 <= track.kept_points <= gpx.MAX_POINTS
    (line,) = track.lines
    # the ends stay
    assert line[0][0] == 7.0
    assert line[-1][0] == round(7 + 4999 * 1e-5, 6)


@pytest.mark.parametrize(
    ('body', 'message'),
    [
        # XXE: an external entity
        (
            b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY x SYSTEM '
            b'"file:///etc/passwd">]><gpx><trk><trkseg><trkpt lat="1" lon="1">'
            b'<name>&x;</name></trkpt></trkseg></trk></gpx>',
            'refused',
        ),
        # billion laughs
        (
            b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
            b'<gpx>&lol2;</gpx>',
            'refused',
        ),
        # a DTD alone
        (
            b'<?xml version="1.0"?><!DOCTYPE gpx SYSTEM "http://x/gpx.dtd"><gpx/>',
            'refused',
        ),
        (b'not xml at all', 'not XML'),
        (b'<gpx><trk><trkseg><trkpt lat="1" lon="1">', 'not XML'),
        (b'<kml><Placemark/></kml>', 'not a GPX'),
        (doc('<trk><trkseg></trkseg></trk>'), 'no line'),
        (doc('<wpt lat="45" lon="7"/>'), 'no line'),
        (b'\xff\xfe\x00garbage', 'not XML'),
    ],
)
def test_hostile_or_useless_files_are_refused(body, message):
    with pytest.raises(gpx.GpxError, match=message):
        gpx.parse(body)


def test_size_cap():
    with pytest.raises(gpx.GpxError, match='too large'):
        gpx.parse(b' ' * (gpx.MAX_BYTES + 1))
    with pytest.raises(gpx.GpxError, match='not bytes'):
        gpx.parse('text')


def test_point_cap(monkeypatch):
    monkeypatch.setattr(gpx, 'MAX_RAW_POINTS', 3)
    points = segment(*[(7, 45 + i / 100) for i in range(4)])
    with pytest.raises(gpx.GpxError, match='too many points'):
        gpx.parse(doc(f'<trk><trkseg>{points}</trkseg></trk>'))
