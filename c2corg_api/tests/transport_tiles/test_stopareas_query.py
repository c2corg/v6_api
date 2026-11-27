"""The tiles generator (transport_tiles/) reads the stop areas with its own SQL.

It lives next to the API so that a change of the table breaks this test, and
not the monthly job.
"""

from sqlalchemy import func, text

from c2corg_api.models.stoparea import Stoparea
from transport_tiles import merge_stopareas


class TestStopareasQuery:
    def test_query_reads_the_columns_of_the_stoparea_table(self, session):
        session.add_all(
            [
                Stoparea(
                    stoparea_id=9301,
                    navitia_id='stop_area:TEST:9301',
                    stoparea_name='Gare du lac',
                    line='A',
                    operator='Sibra',
                    # the column is in web mercator (3857), like the other positions
                    geom=func.ST_Transform(
                        func.ST_SetSRID(func.ST_MakePoint(6.1234, 45.9012), 4326), 3857
                    ),
                ),
                Stoparea(
                    stoparea_id=9302,
                    navitia_id='stop_area:TEST:9302',
                    stoparea_name='Sans position',
                    line='B',
                    operator='Sibra',
                ),
            ]
        )
        session.flush()

        rows = session.execute(text(merge_stopareas.QUERY)).mappings().all()

        ours = [row for row in rows if row['navitia_id'].startswith('stop_area:TEST:')]
        # a stop area without position cannot be drawn
        assert [row['navitia_id'] for row in ours] == ['stop_area:TEST:9301']
        row = ours[0]
        assert row['stoparea_name'] == 'Gare du lac'
        assert row['line'] == 'A'
        assert row['operator'] == 'Sibra'
        assert round(row['lon'], 4) == 6.1234
        assert round(row['lat'], 4) == 45.9012

    def test_the_stop_areas_merge_with_the_stops_of_the_map(self):
        stop = {
            'type': 'Feature',
            'properties': {'name': 'Gare du lac', 'lines': 'A', 'modes': 'bus'},
            'geometry': {'type': 'Point', 'coordinates': [6.1235, 45.9012]},
        }
        stopareas = [
            {
                'navitia_id': 'stop_area:TEST:9301',
                'name': 'Gare du lac',
                'line': 'A',
                'operator': 'Sibra',
                'lon': 6.1234,
                'lat': 45.9012,
            }
        ]

        merged = list(merge_stopareas.merge([stop], stopareas))

        assert len(merged) == 1
        assert merged[0]['properties']['navitia_id'] == 'stop_area:TEST:9301'
