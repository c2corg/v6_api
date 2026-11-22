"""The avalanche bulletins of the EAWS regions, as CAAML v6 JSON."""
# The French massifs from Météo-France (c2corg/v6_api#2681), whose numbers are
# the EAWS region ids FR-01 to FR-74; the regions of the Alps and the Pyrenees
# whose services publish CAAML v6 (#2683). The latest bulletin only, for now:
# the bulletin of a day will be /regions/{region_id}/{YYYY-MM-DD} (#2686), the
# day it is valid for, as the EAWS services name their files.

from typing import Annotated

from fastapi import Path, Query, Response

from c2corg_api.avalanche_bulletins import meteofrance
from c2corg_api.avalanche_bulletins.cache import UpstreamError
from c2corg_api.avalanche_bulletins.regions import UnknownRegion, latest_bulletins
from c2corg_api.httpexceptions import HTTPNotFound, HTTPServiceUnavailable
from c2corg_api.web.answers import http_error
from c2corg_api.web.params import Lang

RegionId = Annotated[
    str,
    Path(
        description='The EAWS region id: `FR-03` (a massif of Météo-France), '
        '`CH-4231`, `AT-07-14-01`... or a region holding others (`CH`).',
        pattern=r'^[A-Z]{2}(-[A-Z0-9]{1,6}){0,4}$',
    ),
]
BulletinLang = Annotated[
    Lang | None,
    Query(
        description='The language of the bulletin, if its service publishes it '
        '(else English). Météo-France publishes in French only.'
    ),
]

# the API cache follows the publications, the browsers keep a bulletin briefly
CACHE_CONTROL = 'public, max-age=300'


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, endpoint in (
        ('/avalanche-bulletins/regions/{region_id}/latest', avalanche_bulletin),
        (
            '/avalanche-bulletins/regions/{region_id}/latest/pdf',
            avalanche_bulletin_pdf,
        ),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['avalanche-bulletins'],
        )


def avalanche_bulletin(
    region_id: RegionId, response: Response, lang: BulletinLang = None
):
    """Return the last bulletins published for a region, as CAAML v6."""
    try:
        bulletins = latest_bulletins(region_id, lang)
    except UnknownRegion:
        return http_error(HTTPNotFound('no avalanche bulletin for this region'))
    except UpstreamError:
        return http_error(HTTPServiceUnavailable('the bulletin service did not answer'))
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {'bulletins': bulletins}


def avalanche_bulletin_pdf(region_id: RegionId):
    """Return the official PDF of the last bulletin of a French massif."""
    massif = meteofrance.massif_of(region_id)
    if massif is None:
        return http_error(HTTPNotFound('no PDF bulletin for this region'))
    try:
        content = meteofrance.pdf(massif)
    except UpstreamError:
        return http_error(HTTPServiceUnavailable('Météo-France did not answer'))
    if content is None:
        return http_error(HTTPNotFound('no avalanche bulletin for this region now'))
    return Response(
        content,
        media_type='application/pdf',
        headers={
            'Cache-Control': CACHE_CONTROL,
            'Content-Disposition': f'inline; filename="BRA-{region_id}.pdf"',
        },
    )


for endpoint in (avalanche_bulletin, avalanche_bulletin_pdf):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
