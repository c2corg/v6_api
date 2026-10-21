# ruff: noqa: E501
"""A small GTFS archive for the tests."""
import io
import zipfile
from datetime import date

# a Wednesday: the timetables start this day (bit 0)
TODAY = date(2026, 10, 21)

_FILES = {
    'agency.txt': """agency_id,agency_name,agency_url,agency_timezone
A,Bus Alpes,https://example.org,Europe/Paris
""",
    'routes.txt': """route_id,agency_id,route_short_name,route_long_name,route_type,route_color,route_text_color,route_url
R1,A,1,Gare - Col,3,FF0000,000000,https://example.org/r1
R2,A,TER,Gare - Col (train),2,,,
""",
    'stops.txt': """stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,stop_code
S1,Gare,45.0000,6.0000,1,,
S1a,Gare quai A,45.0001,6.0001,0,S1,QA
S2,Mairie,45.0100,6.0100,0,,
S3,Col,45.0200,6.0200,0,,
S4,Hameau,45.0300,6.0300,0,,
""",
    'calendar.txt': """service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
WK,1,1,1,1,1,0,0,20261001,20271231
SAT,0,0,0,0,0,1,0,20261001,20271231
""",
    # no service on Friday 23 October, a Saturday service on Sunday 25
    'calendar_dates.txt': """service_id,date,exception_type
WK,20261023,2
SAT,20261025,1
""",
    'trips.txt': """route_id,service_id,trip_id,direction_id,trip_headsign,shape_id
R1,WK,T1,0,Col,SH1
R1,WK,T2,0,Col,SH1
R1,WK,T3,1,Gare,SH1
R1,SAT,T4,0,Mairie,SH1
R2,WK,T5,0,Col,
""",
    'stop_times.txt': """trip_id,arrival_time,departure_time,stop_id,stop_sequence
T1,08:00:00,08:00:00,S1a,1
T1,08:10:00,08:10:00,S2,2
T1,08:25:00,08:25:00,S3,3
T2,17:00:00,17:00:00,S1a,1
T2,17:10:00,17:10:00,S2,2
T2,25:10:00,25:10:00,S3,3
T3,09:00:00,09:00:00,S3,1
T3,09:15:00,09:15:00,S2,2
T3,09:25:00,09:25:00,S1a,3
T4,12:00:00,12:00:00,S1a,1
T4,12:10:00,12:10:00,S2,2
T5,10:00:00,10:00:00,S1,1
T5,10:40:00,10:40:00,S3,2
""",
    # eleven points along a straight line: simplification removes the middle
    # ones
    'shapes.txt': """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
SH1,45.0000,6.0000,1
SH1,45.0020,6.0020,2
SH1,45.0040,6.0040,3
SH1,45.0060,6.0060,4
SH1,45.0080,6.0080,5
SH1,45.0100,6.0100,6
SH1,45.0120,6.0120,7
SH1,45.0140,6.0140,8
SH1,45.0160,6.0160,9
SH1,45.0180,6.0180,10
SH1,45.0200,6.0200,11
""",
}


def gtfs_archive(**overrides):
    """The archive as a file object; `overrides` replace files (name
    without .txt)."""
    files = dict(_FILES)
    for name, content in overrides.items():
        files[name + '.txt'] = content
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return io.BytesIO(buffer.getvalue())
