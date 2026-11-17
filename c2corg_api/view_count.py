"""Count the views of the documents, buffered in Redis.

A read of a document must not write to the database (#1502): each view only
increments the counter of the document in a Redis hash (HINCRBY), and the
`increment_documents_views` job adds the counters to the `view_count` column
of the documents every few minutes, a few thousand documents per transaction
(see c2corg_api/jobs/increment_documents_views.py).

Redis being down only loses views: the reads go on, without asking Redis
again for a while (as the cache does, see caching.CacheStatus).
"""

import logging
import time

import redis
from sqlalchemy import text

from c2corg_api.caching import CacheStatus
from c2corg_api.crawler.crawler_service import is_crawler

log = logging.getLogger(__name__)

# the most documents updated by one transaction
BATCH_SIZE = 4000

# seconds between two transactions, not to hold the locks of the documents
# rows for too long
PAUSE = 2

_INCREMENT = text(
    """
    UPDATE guidebook.documents AS d
    SET view_count = d.view_count + v.views
    FROM unnest(CAST(:ids AS integer[]), CAST(:views AS integer[]))
        AS v(document_id, views)
    WHERE d.document_id = v.document_id
"""
)


class ViewCounter:
    """The counters of the views of the documents not yet in the database."""

    def __init__(self, client, key, refresh_period=30):
        self.redis = client
        # the hash of the views counted since the last run of the job
        self.key = key
        # the hash the job is adding to the database: left by a failed run,
        # it is added again by the next one
        self.processing_key = f'{key}_processing'
        self.status = CacheStatus(refresh_period)

    @classmethod
    def from_settings(cls, settings):
        """Return the counter of the Redis queue database of the settings."""
        url = '{}?db={}'.format(settings['redis.url'], settings['redis.db_queue'])
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=float(settings['redis.socket_connect_timeout']),
            socket_timeout=float(settings['redis.socket_timeout']),
        )
        return cls(
            client,
            settings['redis.documents_views_key'],
            int(settings.get('redis.cache_status_refresh_period') or 30),
        )

    def count(self, document_id):
        """Count a view of a document; never fails, a view is lost at worst."""
        if self.status.is_down():
            return
        try:
            self.redis.hincrby(self.key, document_id, 1)
        except redis.RedisError:
            log.warning('Could not count a view of %d', document_id, exc_info=True)
            self.status.request_failure()
        else:
            self.status.request_success()

    def flush(self, session, batch_size=BATCH_SIZE, pause=PAUSE):
        """Add the counted views to the database; return how many."""
        if not self.redis.exists(self.processing_key):
            try:
                # atomic: the views counted from now on go to a new hash
                self.redis.rename(self.key, self.processing_key)
            except redis.ResponseError:
                # no such key: no view since the last run
                return 0

        counters = self.redis.hgetall(self.processing_key)
        views = sorted(_parse(counters))
        total = 0
        for start in range(0, len(views), batch_size):
            if start and pause:
                time.sleep(pause)
            batch = views[start : start + batch_size]
            session.execute(
                _INCREMENT,
                {
                    'ids': [document_id for document_id, _, _ in batch],
                    'views': [count for _, count, _ in batch],
                },
            )
            session.commit()
            # committed: not to be added again if a later batch fails
            self.redis.hdel(self.processing_key, *(field for _, _, field in batch))
            total += sum(count for _, count, _ in batch)

        # what is left was not a counter
        self.redis.delete(self.processing_key)
        log.info('Added %d views of %d documents', total, len(views))
        return total


def _parse(counters):
    """Yield (document id, views, field) for the fields of the hash."""
    for field, value in counters.items():
        try:
            yield int(field), int(value), field
        except ValueError:
            log.warning('Ignoring the views counter %r: %r', field, value)


def count_view(request, document_id):
    """Count a read of a document, unless a bot or a crawler made it."""
    if request.is_robot or is_crawler(request.headers.get('User-Agent')):
        return
    counter = getattr(request.registry, 'view_counter', None)
    if counter is not None:
        counter.count(document_id)
