"""Relevance regression tests of the title search (the search box)."""

# Each case is a query typed by a user, taken from a forum report, with what
# the user expected. The corpus holds the expected documents and the unrelated
# titles that used to outrank them ("decoys"). A failing case means a change of
# the query, the analyzers or the mapping brought an old complaint back.
#
# Sources:
#
# - [342561] https://forum.camptocamp.org/t/342561
#   "[Bug] Recherche topoguide - résultats non pertinents" (2025)
# - [319862] https://forum.camptocamp.org/t/319862
#   "Topoguide - recherche par chaîne de caractères dans le titre plus assez
#   sélective" (2023)
#
# Cases with the source 'own' are not reported problems but behaviours users
# rely on (accents, elisions, stemming, titles in another language...).
#
# To add a case: add the documents to CORPUS (keep the real titles, decoys
# included) and a Case to CASES, citing its source.
#
# The corpus is small: term frequencies differ a lot from the production
# index, so a case passing here may still rank badly in production (e.g.
# "Lau Bij" passes even with the query used before 2026-11-11). Prefer
# assertions on what must be absent over fine-grained ranking.

from dataclasses import dataclass
from urllib.parse import urlencode

import pytest

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.search import reset_search_index

# what the search box of the UI asks for
LIMIT = 10


@dataclass(frozen=True)
class Doc:
    """A document of the corpus: a waypoint ('w') or a route ('r')."""

    type: str
    # {lang: title}, or {lang: (title_prefix, title)} for a route
    titles: dict


def _wp(title, **others):
    return Doc('w', {'fr': title, **others})


def _route(prefix, title):
    return Doc('r', {'fr': (prefix, title)})


CORPUS = {
    # [342561] "Lau Bij": "Lau" matched "Laura", "Bij" matched "Bijou",
    # "Biju" or, stemmed, "bivouac"; the route was not in the results
    'lau_bij': _route('Cogne - Valeille', 'Lau Bij'),
    'laura': _route('Pointe Laura', 'Voie normale'),
    'bijou': _route('Aiguille du Bijou', 'Arête sud'),
    'biju': _route('Piz Biju', 'Face nord'),
    'bivouac_lama': _route('Bivouac du Lama', 'Par le vallon'),
    'cogne': _wp('Cogne'),
    # [342561] "Olan": the routes of the Olan came far down the list, the
    # "O" looked ignored
    'olan': _wp('Olan'),
    'olan_normale': _route('Olan', "Voie normale par le refuge de l'Olan"),
    'olan_nw': _route('Olan', 'Pilier nord-ouest'),
    'col_lans': _wp('Col de Lans'),
    'lanchatra': _wp('Lanchâtra'),
    'pic_lan': _wp('Pic de Lan'),
    # [319862] "Aiguille du Midi" also found "Aiguilles du Diable - Pointe
    # Médiane"; "L'Aiguillon" gave 36 results instead of 4
    'aiguille_midi': _wp('Aiguille du Midi'),
    'aiguilles_diable': _wp('Aiguilles du Diable - Pointe Médiane'),
    'aiguillon': _wp("L'Aiguillon"),
    'aiguillon_route': _route("L'Aiguillon", 'Arête est'),
    'aiguille_verte': _wp('Aiguille Verte'),
    'grande_hoche': _wp('Col de la Grande Hoche'),
    # [319862] "(GRV)" found "Grenoble", "Gavarnie", "Grand Combin"...
    'grv': _route('Saas-Fee', 'Grande Randonnée Valaisanne (GRV)'),
    'grenoble': _wp('Grenoble'),
    'gavarnie': _wp('Gavarnie'),
    'grand_combin': _wp('Grand Combin'),
    # [319862] "Goléon" did not find the Goléon, "Refuge du Goleon" did
    'refuge_goleon': _wp('Refuge du Goléon'),
    'aiguille_goleon': _wp('Aiguille du Goléon'),
    'galibier': _wp('Col du Galibier'),
    # [319862] "colonney" found "Volonne"
    'colonney': _wp('Colonney'),
    'volonne': _wp('Volonne'),
    # [319862] "Sormiuo" (a typo) found "Bormio"
    'sormiou': _wp('Calanque de Sormiou'),
    'bormio': _wp('Bormio'),
    # [319862] "saleve"
    'saleve': _wp('Salève'),
    'salle': _wp('Pointe de la Salle'),
    # [319862] "cog" found Cogne "far away", after "col..."
    'col_croix': _wp('Col de la Croix'),
    'col_coq': _wp('Col du Coq'),
    # [319862] "Matterhorn" must find the Cervin, whatever the language
    'cervin': _wp('Cervin', en='Matterhorn', it='Cervino', de='Matterhorn'),
    # own cases: behaviours users rely on, not reported yet
    'barre_ecrins': _wp('Barre des Écrins'),
    'dome_ecrins': _wp('Dôme de Neige des Écrins'),
    'ecrins_normale': _route('Barre des Écrins', 'Voie normale'),
    'mb_normale': _route('Mont Blanc', 'Voie normale par le Goûter'),
    'barre_noire': _wp('Barre Noire'),
    'dent_herens': _wp("Dent d'Hérens"),
    'dent_blanche': _wp('Dent Blanche'),
    'aiguilles_rouges': _wp("Aiguilles Rouges d'Arolla"),
    'lavaredo': Doc('w', {'it': 'Cima Grande di Lavaredo'}),
    'montana_negra': Doc('w', {'es': 'Montaña Negra'}),
    'grunhorn': Doc('w', {'de': 'Gross Grünhorn'}),
    'st_jean': _wp('Saint-Jean-de-Maurienne'),
    'jorasses': _wp('Grandes Jorasses'),
    'grande_casse': _wp('Grande Casse'),
}


@dataclass(frozen=True)
class Case:
    """A query and what the user expects from it."""

    query: str
    type: str
    source: str
    # the document that must come first
    first: str | None = None
    # documents that must be in the results
    found: tuple = ()
    # documents that must not be in the results
    absent: tuple = ()
    # why the search does not do it yet: the case is expected to fail, and
    # must be turned into a normal case once it passes
    missing: str | None = None


CASES = [
    Case('Lau Bij', 'r', '342561', first='lau_bij'),
    Case('lau bij', 'r', '342561', first='lau_bij'),
    Case('lau bi', 'r', '342561', first='lau_bij'),
    Case('Lau Bij', 'r', '342561', absent=('laura', 'bijou', 'biju', 'bivouac_lama')),
    Case(
        'Olan', 'w', '342561', first='olan', absent=('col_lans', 'lanchatra', 'pic_lan')
    ),
    Case('Olan', 'r', '342561', found=('olan_normale', 'olan_nw')),
    Case(
        'Aiguille du Midi',
        'w',
        '319862',
        first='aiguille_midi',
        absent=('aiguilles_diable',),
    ),
    Case('Aiguille', 'w', '319862', absent=('grande_hoche',)),
    Case(
        "L'Aiguillon",
        'w',
        '319862',
        first='aiguillon',
        absent=('aiguille_verte', 'aiguille_midi'),
    ),
    Case("L'Aiguillon", 'r', '319862', first='aiguillon_route'),
    Case('(GRV)', 'r', '319862', first='grv'),
    Case('(GRV)', 'w', '319862', absent=('grenoble', 'gavarnie', 'grand_combin')),
    Case(
        'Goléon',
        'w',
        '319862',
        found=('refuge_goleon', 'aiguille_goleon'),
        absent=('galibier',),
    ),
    Case('goleon', 'w', '319862', found=('refuge_goleon', 'aiguille_goleon')),
    Case('Refuge du Goleon', 'w', '319862', first='refuge_goleon'),
    Case('colonney', 'w', '319862', first='colonney', absent=('volonne',)),
    Case('Sormiou', 'w', '319862', first='sormiou'),
    Case('Sormiuo', 'w', '319862', first='sormiou', absent=('bormio',)),
    Case('saleve', 'w', '319862', first='saleve', absent=('salle',)),
    Case('cog', 'w', '319862', first='cogne', absent=('col_croix', 'col_coq')),
    Case('Matterhorn', 'w', '319862', first='cervin'),
    Case('Cervino', 'w', '319862', first='cervin'),
    # own cases
    Case(
        'ecrins',
        'w',
        'own',
        found=('barre_ecrins', 'dome_ecrins'),
        absent=('barre_noire',),
    ),
    Case('BARRE DES ECRINS', 'w', 'own', first='barre_ecrins'),
    Case('barre des ecr', 'w', 'own', first='barre_ecrins', absent=('barre_noire',)),
    Case('ecrins barre', 'w', 'own', first='barre_ecrins'),
    Case('ecrins normale', 'r', 'own', first='ecrins_normale', absent=('mb_normale',)),
    Case('herens', 'w', 'own', first='dent_herens', absent=('dent_blanche',)),
    Case("dent d'herens", 'w', 'own', first='dent_herens'),
    Case('dent herens', 'w', 'own', first='dent_herens'),
    Case('aiguille rouge', 'w', 'own', first='aiguilles_rouges'),
    Case('lavaredo', 'w', 'own', first='lavaredo'),
    Case('montana negra', 'w', 'own', first='montana_negra'),
    Case('grunhorn', 'w', 'own', first='grunhorn'),
    Case('grünhorn', 'w', 'own', first='grunhorn'),
    Case('saint jean', 'w', 'own', first='st_jean'),
    Case(
        'st jean',
        'w',
        'own',
        first='st_jean',
        missing='no synonyms: "st" is not "saint"',
    ),
    Case('jorases', 'w', 'own', first='jorasses', absent=('grande_casse',)),
    Case('grandes jorasses', 'w', 'own', first='jorasses', absent=('grande_casse',)),
]


def _make(doc):
    if doc.type == 'w':
        return Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(lang=lang, title=title)
                for lang, title in doc.titles.items()
            ],
        )
    return Route(
        activities=['mountain_climbing'],
        elevation_max=3000,
        elevation_min=2000,
        locales=[
            RouteLocale(lang=lang, title_prefix=prefix, title=title)
            for lang, (prefix, title) in doc.titles.items()
        ],
    )


@pytest.fixture
def corpus(session):
    """Index the corpus alone, return the document id of each key."""
    documents = {key: _make(doc) for key, doc in CORPUS.items()}
    session.add_all(documents.values())
    session.flush()
    # a new index: the documents of the previous tests are rolled back in the
    # database but stay in the index, and would push the corpus out of the
    # results
    reset_search_index(session)
    return {key: doc.document_id for key, doc in documents.items()}


_RESULT_KEYS = {'w': 'waypoints', 'r': 'routes'}


def _search(client, query, type_):
    params = urlencode({'q': query, 't': type_, 'pl': 'fr', 'limit': LIMIT})
    response = client.get(f'/search?{params}', status=200)
    return [
        doc['document_id'] for doc in response.json[_RESULT_KEYS[type_]]['documents']
    ]


def _case_id(case):
    return f'{case.source}-{case.type}-{case.query}'


def _params():
    for case in CASES:
        marks = (
            [pytest.mark.xfail(reason=case.missing, strict=True)]
            if case.missing
            else []
        )
        yield pytest.param(case, marks=marks, id=_case_id(case))


@pytest.mark.parametrize('case', list(_params()))
def test_relevance(client, corpus, case):
    ids = _search(client, case.query, case.type)
    key_of = {v: k for k, v in corpus.items()}
    got = [key_of.get(i, i) for i in ids]

    if case.first:
        assert got[:1] == [case.first], f'{case.query!r} -> {got}'
    for key in case.found:
        assert key in got, f'{case.query!r} -> {got}, {key} missing'
    for key in case.absent:
        assert key not in got, f'{case.query!r} -> {got}, {key} found'
