"""Load test scenarios of the API, for Locust (see README.md)."""
# Two kinds of users, as on camptocamp.org:
# - Visitor: an anonymous visitor reading the guidebook (documents, cooked
#   documents, listings, search, history, the feed);
# - Contributor: a logged-in user (accounts made by create_test_users.py),
#   who also reads their account, preferences and personal feed, and, with
#   C2C_WRITES=1, follows and unfollows another user (writes that leave no
#   trace).
# Only Locust and the standard library: it runs outside of the project's
# environment (urllib3 is held below 2 there), with
#   uvx --from locust==2.46.7 locust -f c2corg_api/scripts/loadtests/locustfile.py

import json
import os
import random
import urllib.request

from locust import HttpUser, between, events, task

TYPES = ['waypoints', 'routes', 'outings', 'images', 'areas', 'articles']
WORDS = ['mont', 'aiguille', 'col', 'lac', 'pointe', 'refuge', 'arete', 'face']
LANGS = ['fr', 'en', 'it', 'de', 'es']

# picks the requests of the load test, not a secret
_random = random.Random()  # nosec B311

# the test accounts of create_test_users.py: testuserc2c<n>, password = username
USERNAME = os.environ.get('C2C_USERNAME', 'testuserc2c')
USERS = int(os.environ.get('C2C_USERS', '1000'))
WRITES = os.environ.get('C2C_WRITES') == '1'

# {type: [document ids]}, read from the listings when the test starts
DOCUMENTS = {}
# user ids of the test accounts that logged in, to follow one another
USER_IDS = []


@events.test_start.add_listener
def read_document_ids(environment, **kwargs):
    """Read the ids of the documents the users will read."""
    for doc_type in TYPES:
        url = f'{environment.host}/{doc_type}?limit=100'
        with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310
            documents = json.load(response).get('documents', [])
        if documents:
            DOCUMENTS[doc_type] = [d['document_id'] for d in documents]
    if not DOCUMENTS:
        raise RuntimeError(f'no document found in the listings of {environment.host}')


def _document():
    """Return (type, id) of a document to read."""
    doc_type = _random.choice(list(DOCUMENTS))
    return doc_type, _random.choice(DOCUMENTS[doc_type])


class Reader(HttpUser):
    """The reading tasks of every user."""

    abstract = True

    def headers(self):
        return {}

    @task(40)
    def document(self):
        doc_type, document_id = _document()
        self.client.get(
            f'/{doc_type}/{document_id}?l={_random.choice(LANGS)}',
            name=f'/{doc_type}/[id]',
            headers=self.headers(),
        )

    @task(10)
    def cooked_document(self):
        doc_type, document_id = _document()
        self.client.get(
            f'/{doc_type}/{document_id}?cook={_random.choice(LANGS)}',
            name=f'/{doc_type}/[id]?cook',
            headers=self.headers(),
        )

    @task(25)
    def listing(self):
        doc_type = _random.choice(list(DOCUMENTS))
        offset = _random.choice([0, 0, 0, 30, 60])
        self.client.get(
            f'/{doc_type}?limit=30&offset={offset}&pl={_random.choice(LANGS)}',
            name=f'/{doc_type}',
            headers=self.headers(),
        )

    @task(15)
    def search(self):
        self.client.get(
            f'/search?q={_random.choice(WORDS)}&pl={_random.choice(LANGS)}',
            name='/search',
            headers=self.headers(),
        )

    @task(5)
    def history(self):
        _, document_id = _document()
        self.client.get(
            f'/document/{document_id}/history/fr',
            name='/document/[id]/history/[lang]',
            headers=self.headers(),
        )

    @task(5)
    def feed(self):
        self.client.get(
            f'/feed?pl={_random.choice(LANGS)}', name='/feed', headers=self.headers()
        )


class Visitor(Reader):
    """An anonymous visitor reading the guidebook."""

    weight = 9
    wait_time = between(1, 5)


class Contributor(Reader):
    """A logged-in user, who also reads (and, with C2C_WRITES=1, writes)."""

    weight = 1
    wait_time = between(2, 8)

    def on_start(self):
        username = f'{USERNAME}{_random.randint(1, USERS)}'
        response = self.client.post(
            '/users/login',
            json={'username': username, 'password': username},
            name='/users/login',
        )
        if response.status_code != 200:
            # e.g. 429: the logins are rate limited per client IP
            self.token = None
            self.user_id = None
            return
        self.token = response.json()['token']
        self.user_id = response.json()['id']
        USER_IDS.append(self.user_id)

    def headers(self):
        return {'Authorization': f'JWT token="{self.token}"'} if self.token else {}

    @task(5)
    def account(self):
        if self.token:
            self.client.get('/users/account', headers=self.headers())

    @task(5)
    def personal_feed(self):
        if self.token:
            self.client.get('/personal-feed?pl=fr', headers=self.headers())

    @task(3)
    def preferences(self):
        if self.token:
            self.client.get('/users/preferences', headers=self.headers())

    @task(3)
    def follow_and_unfollow(self):
        others = [u for u in USER_IDS if u != self.user_id]
        if not (WRITES and self.token and others):
            return
        body = {'user_id': _random.choice(others)}
        self.client.post('/users/follow', json=body, headers=self.headers())
        self.client.post('/users/unfollow', json=body, headers=self.headers())
