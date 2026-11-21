"""The avalanche bulletins: Météo-France's, as CAAML v6 JSON, and its PDF."""
# Only the French massifs for now: the EAWS region ids FR-01 to FR-74 are the
# numbers of the Météo-France massifs (c2corg/v6_api#2681).

from typing import Annotated

from fastapi import Path, Response

from c2corg_api.avalanche_bulletins import meteofrance
from c2corg_api.httpexceptions import HTTPNotFound, HTTPServiceUnavailable
from c2corg_api.web.answers import http_error

RegionId = Annotated[
    str,
    Path(
        description='The EAWS region id: `FR-01` to `FR-74`, the massifs of '
        'Météo-France.',
        pattern=r'^FR-\d{2}$',
    ),
]

# the API cache follows the publications, the browsers keep a bulletin briefly
CACHE_CONTROL = 'public, max-age=300'


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, endpoint in (
        ('/avalanche-bulletins/regions/{region_id}', avalanche_bulletin),
        ('/avalanche-bulletins/regions/{region_id}/pdf', avalanche_bulletin_pdf),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['avalanche-bulletins'],
        )


def avalanche_bulletin(region_id: RegionId, response: Response):
    """Return the bulletin of a region as CAAML v6: none out of season."""
    massif = meteofrance.massif_of(region_id)
    if massif is None:
        return http_error(HTTPNotFound('no avalanche bulletin for this region'))
    try:
        bulletins = meteofrance.bulletin(massif)
    except meteofrance.UpstreamError:
        return http_error(HTTPServiceUnavailable('Météo-France did not answer'))
    response.headers['Cache-Control'] = CACHE_CONTROL
    return bulletins


def avalanche_bulletin_pdf(region_id: RegionId):
    """Return the official PDF of the bulletin of a region."""
    massif = meteofrance.massif_of(region_id)
    if massif is None:
        return http_error(HTTPNotFound('no avalanche bulletin for this region'))
    try:
        content = meteofrance.pdf(massif)
    except meteofrance.UpstreamError:
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
