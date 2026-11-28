"""TEMPORARY: the transports of the backfill of the partner outings.

Delete with the other `backfill_*` files once the history is imported
(c2corg/v6_api#2763).

They are the transports of the harvest (`partners.transport`), with a POST for
the one source whose older reports are only listed by a form (gipfelbuch.ch),
and a User-Agent telling the partner that this is the backfill.
"""

from urllib.parse import urlsplit

import requests

from c2corg_api.partners.adapter import SourceDown
from c2corg_api.partners.transport import (
    FixtureTransport,
    HttpResponse,
    HttpTransport,
    classify,
)


class BackfillHttpTransport(HttpTransport):
    """`HttpTransport` (politeness, budget, classification) plus `post`.

    The cookies of a run are kept by the `requests.Session`: a form token read
    by a GET is valid for the POSTs of the same run.
    """

    USER_AGENT = 'camptocamp.org partner-index backfill (+https://www.camptocamp.org)'

    def post(self, url, *, data, headers=None) -> HttpResponse:
        # the same steps as `HttpTransport.get`, with a POST
        if self._count >= self.rate.max_requests_per_run:
            raise SourceDown('request budget exhausted')
        self._wait(url)
        request_headers = {'User-Agent': self.USER_AGENT, **(headers or {})}
        try:
            raw = self.session.post(
                url,
                data=data,
                headers=request_headers,
                timeout=(5, self.rate.timeout_s),
            )
        except requests.Timeout as e:
            raise SourceDown(f'timeout on {url}') from e
        except requests.ConnectionError as e:
            raise SourceDown(f'connection error on {url}') from e
        except requests.RequestException as e:
            raise SourceDown(f'{type(e).__name__} on {url}') from e
        self._last_request[_host(url)] = self._clock()
        return classify(
            HttpResponse(
                status=raw.status_code,
                headers=dict(raw.headers),
                body=raw.content,
                url=str(raw.url or url),
            )
        )

    def _wait(self, url):
        host = _host(url)
        last = self._last_request.get(host)
        if last is not None:
            wait = self.rate.min_interval_s - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._count += 1
        self._last_request[host] = self._clock()


class BackfillFixtureTransport(FixtureTransport):
    """`FixtureTransport` plus `post`: the form fields match like query params.

    A manifest entry lists only the fields that tell the answers apart (an
    offset): a volatile field (a form token) does not have to match.
    """

    def post(self, url, *, data, headers=None) -> HttpResponse:
        return self.get(url, params=data, headers=headers)


def _host(url):
    return urlsplit(url).netloc.lower()
