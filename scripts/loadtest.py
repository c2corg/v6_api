"""Replay a mix of API read requests and report throughput and latencies."""
# A small load test to compare two versions of the API on the same machine
# and data (e.g. before and after a route moves to FastAPI, #2365): it is not
# a capacity test. Only the standard library, no installation.
#
#   python scripts/loadtest.py http://localhost:6543 --threads 8 --duration 60
#
# It first reads some document ids from the listings, then the threads send
# requests drawn from MIX for the given duration, and it prints, per kind of
# request: count, errors, mean, p50, p95 and p99 latencies, and the overall
# throughput. Run it twice against the same data to see the noise.

import argparse
import http.client
import json
import random
import statistics
import threading
import time
import urllib.parse

# (kind, weight, path template): {id} is a document id of the listing,
# {type} its URL prefix
MIX = [
    ('document', 40, '/{type}/{id}?l=fr'),
    ('cooked document', 10, '/{type}/{id}?cook=fr'),
    ('listing', 25, '/{type}?limit=30&pl=fr'),
    ('search', 15, '/search?q={word}&pl=fr'),
    ('history', 5, '/document/{id}/history/fr'),
    ('health', 5, '/health'),
]
TYPES = ['waypoints', 'routes', 'outings', 'images', 'areas', 'articles']
WORDS = ['mont', 'aiguille', 'col', 'lac', 'pointe', 'refuge', 'arete', 'face']


def _get(base, path, timeout=30):
    url = urllib.parse.urlsplit(base)
    connection_class = (
        http.client.HTTPSConnection
        if url.scheme == 'https'
        else http.client.HTTPConnection
    )
    connection = connection_class(url.netloc, timeout=timeout)
    try:
        connection.request('GET', path, headers={'Accept': 'application/json'})
        response = connection.getresponse()
        body = response.read()
        return response.status, body
    finally:
        connection.close()


def collect_ids(base, per_type=50):
    """Return {type: [document ids]} from the listings."""
    ids = {}
    for doc_type in TYPES:
        status, body = _get(base, f'/{doc_type}?limit={per_type}')
        documents = json.loads(body).get('documents', []) if status == 200 else []
        if documents:
            ids[doc_type] = [d['document_id'] for d in documents]
    if not ids:
        raise SystemExit('no document found in the listings')
    return ids


def pick(ids, rng):
    """Return (kind, path) drawn from MIX."""
    kind, _, template = rng.choices(MIX, weights=[w for _, w, _ in MIX])[0]
    doc_type = rng.choice(list(ids))
    return kind, template.format(
        type=doc_type, id=rng.choice(ids[doc_type]), word=rng.choice(WORDS)
    )


def run(base, ids, threads, duration, seed):
    results = []  # (kind, ms, ok)
    lock = threading.Lock()
    end = time.monotonic() + duration

    def worker(n):
        rng = random.Random(seed + n)
        local = []
        while time.monotonic() < end:
            kind, path = pick(ids, rng)
            start = time.perf_counter()
            try:
                status, _ = _get(base, path)
                ok = status < 500
            except OSError:
                ok = False
            local.append((kind, (time.perf_counter() - start) * 1000, ok))
        with lock:
            results.extend(local)

    workers = [threading.Thread(target=worker, args=(n,)) for n in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return results


def report(results, duration):
    def line(name, rows):
        times = sorted(ms for _, ms, _ in rows)
        errors = sum(1 for _, _, ok in rows if not ok)

        def pct(p):
            return times[min(len(times) - 1, int(len(times) * p))]

        return (
            f'{name:16} {len(rows):6} {errors:6} {statistics.mean(times):8.1f}'
            f' {pct(0.5):8.1f} {pct(0.95):8.1f} {pct(0.99):8.1f}'
        )

    columns = ['count', 'errors', 'mean', 'p50', 'p95', 'p99']
    print(
        f'{"kind":16} '
        + ' '.join(f'{c:>8}' if i > 1 else f'{c:>6}' for i, c in enumerate(columns))
    )
    for kind in [k for k, _, _ in MIX]:
        rows = [r for r in results if r[0] == kind]
        if rows:
            print(line(kind, rows))
    print(line('all', results))
    print(f'throughput: {len(results) / duration:.1f} requests/s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', help='the API base URL, e.g. http://localhost:6543')
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--duration', type=int, default=60, help='seconds')
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    ids = collect_ids(args.base)
    print(f'{sum(map(len, ids.values()))} documents of {len(ids)} types')
    report(run(args.base, ids, args.threads, args.duration, args.seed), args.duration)


if __name__ == '__main__':
    main()
