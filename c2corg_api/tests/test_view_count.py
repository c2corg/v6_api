from unittest.mock import MagicMock

import pytest
import redis
from apscheduler.schedulers.background import BackgroundScheduler

from c2corg_api.crawler.crawler_service import is_crawler
from c2corg_api.jobs import configure_scheduler_from_config
from c2corg_api.jobs.increment_documents_views import increment_documents_views
from c2corg_api.models.book import Book
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.tests import auth_headers
from c2corg_api.view_count import ViewCounter

FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0'
SAFARI_IPHONE = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
)
CHROME_ANDROID = (
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'
)
GOOGLEBOT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'


@pytest.mark.parametrize('user_agent', [FIREFOX, SAFARI_IPHONE, CHROME_ANDROID])
def test_is_crawler_browser(user_agent):
    assert not is_crawler(user_agent)


@pytest.mark.parametrize(
    'user_agent',
    [
        GOOGLEBOT,
        'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        'Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)',
        'facebookexternalhit/1.1',
        'curl/8.5.0',
        'python-requests/2.32.3',
        'Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/130.0.0.0 Safari/537.36',
        '',
        None,
    ],
)
def test_is_crawler_bot(user_agent):
    assert is_crawler(user_agent)


@pytest.fixture
def view_counter(client):
    """Return the counter of the application, without any view counted."""
    counter = client.registry.view_counter
    counter.redis.delete(counter.key, counter.processing_key)
    yield counter
    counter.redis.delete(counter.key, counter.processing_key)


@pytest.fixture
def book(session):
    book = Book(
        activities=['hiking'],
        book_types=['biography'],
        locales=[DocumentLocale(lang='en', title='Escalades au Thaurac')],
    )
    session.add(book)
    session.flush()
    return book


def counted(counter, document_id):
    value = counter.redis.hget(counter.key, document_id)
    return int(value) if value is not None else 0


def test_read_counts_a_view(client, view_counter, book):
    headers = {'User-Agent': FIREFOX}
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    client.get(f'/books/{book.document_id}?cook=en', headers=headers, status=200)
    assert counted(view_counter, book.document_id) == 2


def test_not_modified_counts_a_view(client, view_counter, book):
    # a browser reading the document again, from its cache
    headers = {'User-Agent': FIREFOX}
    etag = client.get(f'/books/{book.document_id}', headers=headers).headers['ETag']
    headers['If-None-Match'] = etag
    client.get(f'/books/{book.document_id}', headers=headers, status=304)
    assert counted(view_counter, book.document_id) == 2


def test_crawler_read_not_counted(client, view_counter, book):
    headers = {'User-Agent': GOOGLEBOT}
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert counted(view_counter, book.document_id) == 0


def test_robot_read_not_counted(client, view_counter, book):
    headers = auth_headers(username='robot', headers={'User-Agent': FIREFOX})
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert counted(view_counter, book.document_id) == 0


def test_contributor_read_counted(client, view_counter, book):
    headers = auth_headers(username='contributor', headers={'User-Agent': FIREFOX})
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert counted(view_counter, book.document_id) == 1


def test_editing_read_not_counted(client, view_counter, book):
    headers = {'User-Agent': FIREFOX}
    client.get(f'/books/{book.document_id}?e=1', headers=headers, status=200)
    assert counted(view_counter, book.document_id) == 0


def test_unknown_document_not_counted(client, view_counter):
    client.get('/books/-9999', headers={'User-Agent': FIREFOX}, status=404)
    assert view_counter.redis.hlen(view_counter.key) == 0


def test_read_redis_down(client, view_counter, book, monkeypatch):
    # the read is answered, the view is lost; Redis is not asked again for a while
    broken = MagicMock(side_effect=redis.ConnectionError('down'))
    monkeypatch.setattr(view_counter.redis, 'hincrby', broken)
    monkeypatch.setattr(view_counter, 'status', type(view_counter.status)())
    headers = {'User-Agent': FIREFOX}
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert broken.call_count == 1
    assert view_counter.status.is_down()


def view_count(session, document_id):
    session.expire_all()
    return session.get(Document, document_id).view_count


def test_flush(client, view_counter, session, book, monkeypatch):
    headers = {'User-Agent': FIREFOX}
    for _ in range(3):
        client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert view_count(session, book.document_id) == 0

    assert view_counter.flush(session) == 3
    assert view_count(session, book.document_id) == 3
    assert not view_counter.redis.exists(view_counter.key)
    assert not view_counter.redis.exists(view_counter.processing_key)

    # nothing new: nothing to do
    assert view_counter.flush(session) == 0

    client.get(f'/books/{book.document_id}', headers=headers, status=200)
    assert view_counter.flush(session) == 1
    assert view_count(session, book.document_id) == 4


def test_flush_batches(view_counter, session, book):
    other = Book(
        activities=['hiking'],
        book_types=['biography'],
        locales=[DocumentLocale(lang='en', title='Escalades au Thaurac 2')],
    )
    session.add(other)
    session.flush()
    view_counter.redis.hset(
        view_counter.key,
        mapping={
            book.document_id: 5,
            other.document_id: 7,
            # an unknown document, and a field that is not a counter
            -9999: 2,
            'oops': 'x',
        },
    )
    assert view_counter.flush(session, batch_size=1, pause=0) == 14
    assert view_count(session, book.document_id) == 5
    assert view_count(session, other.document_id) == 7
    assert not view_counter.redis.exists(view_counter.processing_key)


def test_flush_resumes_failed_run(view_counter, session, book, monkeypatch):
    # the views of a run failing before the commit are added by the next run,
    # before the views counted since
    view_counter.redis.hset(view_counter.key, book.document_id, 5)
    failing = MagicMock(side_effect=RuntimeError('db down'))
    monkeypatch.setattr(session, 'execute', failing)
    with pytest.raises(RuntimeError):
        view_counter.flush(session)
    monkeypatch.undo()
    view_counter.redis.hincrby(view_counter.key, book.document_id, 1)

    assert view_counter.flush(session) == 5
    assert view_count(session, book.document_id) == 5
    assert view_counter.flush(session) == 1
    assert view_count(session, book.document_id) == 6


def test_increment_documents_views_job(view_counter, session, book):
    view_counter.redis.hset(view_counter.key, book.document_id, 2)
    # the job's session works on the engine of DBSession: here the connection
    # of the test
    assert increment_documents_views(view_counter) == 2
    assert view_count(session, book.document_id) == 2


def test_scheduler_runs_the_job(settings, monkeypatch):
    jobs = []
    monkeypatch.setattr('c2corg_api.jobs.atexit.register', lambda function: None)
    monkeypatch.setattr(BackgroundScheduler, 'start', lambda self: None)
    monkeypatch.setattr(
        BackgroundScheduler,
        'add_job',
        lambda self, func, **kwargs: jobs.append((func, kwargs)),
    )
    configure_scheduler_from_config(settings)
    (kwargs,) = [kw for func, kw in jobs if func is increment_documents_views]
    assert kwargs['trigger'] == 'interval'
    assert isinstance(kwargs['kwargs']['view_counter'], ViewCounter)


def test_from_settings(settings):
    counter = ViewCounter.from_settings(settings)
    assert counter.key == settings['redis.documents_views_key']
    assert counter.redis.connection_pool.connection_kwargs['db'] == int(
        settings['redis.db_queue']
    )
