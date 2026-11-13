"""One log line per request, written by the application (see `c2corg_api.asgi`)."""
# On its sync workers, gunicorn writes the access log; on uvicorn workers,
# this middleware does. The message is the one of gunicorn (same greps), and
# the fields come apart too, for the JSON logs, with the duration.

import logging
import time
from datetime import UTC, datetime

log = logging.getLogger('c2corg_api.access')


class AccessLogMiddleware:
    """Log each HTTP request once its answer is sent."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        # 500 if the application fails before it answers
        response = {'status': 500, 'size': 0}

        async def send_and_measure(message):
            if message['type'] == 'http.response.start':
                response['status'] = message['status']
            elif message['type'] == 'http.response.body':
                response['size'] += len(message.get('body', b''))
            await send(message)

        try:
            await self.app(scope, receive, send_and_measure)
        finally:
            _log(scope, response, time.perf_counter() - start)


def _log(scope, response, duration):
    headers = {
        name.decode('latin-1').lower(): value.decode('latin-1')
        for name, value in scope.get('headers', [])
    }
    client = scope.get('client')
    client_addr = client[0] if client else '-'
    path = (scope.get('raw_path') or scope['path'].encode()).decode('latin-1')
    query = scope.get('query_string', b'').decode('latin-1')
    target = f'{path}?{query}' if query else path
    request_line = f'{scope["method"]} {target} HTTP/{scope.get("http_version", "1.1")}'
    referer = headers.get('referer', '-')
    user_agent = headers.get('user-agent', '-')
    when = datetime.now(UTC).strftime('%d/%b/%Y:%H:%M:%S %z')
    log.info(
        '%s - - [%s] "%s" %s %s "%s" "%s"',
        client_addr,
        when,
        request_line,
        response['status'],
        response['size'],
        referer,
        user_agent,
        extra={
            'client_addr': client_addr,
            'method': scope['method'],
            'path': path,
            'query': query,
            'status': response['status'],
            'size': response['size'],
            'duration_ms': round(duration * 1000, 1),
            'referer': referer,
            'user_agent': user_agent,
        },
    )
