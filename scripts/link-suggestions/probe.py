"""Prototype: find the waypoints and routes named in the texts of the documents but not linked.

Standalone (no API code but `c2corg_api/partners/places.py`, loaded by path), on a database of
the site (the demo one by default):

    uv run --with 'psycopg[binary]' python scripts/link-suggestions/probe.py \
        --dsn postgresql://postgres:test@localhost:5432/c2corg --out /tmp/ls

It writes:

- `suggestions.csv`: one row per (locale, target) named in a text and not linked;
- `recall.csv`: the links already written ([[waypoints/ID|label]], [[routes/ID|label]]), each turned
  back into plain text: found again (right target), found with another target, or missed;
- a summary on stdout.

The modes, from the most to the least reliable (see the README):

- `assoc`: the target is associated with the document, or one hop away (an outing's route's
  waypoints, a route's waypoints' parents...);
- `near`: within --near-km of the document or of one of its associated documents;
- `far`: anywhere else, only when its name designates a single document.
"""

import argparse
import collections
import csv
import importlib.util
import math
import pathlib
import re
import sys
import time
import unicodedata

import psycopg

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    'places', HERE.parents[1] / 'c2corg_api' / 'partners' / 'places.py'
)
places = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(places)

# the text fields of the locales, by table (the title and title_prefix are not texts)
TEXT_FIELDS = {
    'documents_locales': ('summary', 'description'),
    'routes_locales': (
        'remarks',
        'gear',
        'route_history',
        'slope',
        'slackline_anchor1',
        'slackline_anchor2',
    ),
    'outings_locales': (
        'participants',
        'access_comment',
        'weather',
        'timing',
        'conditions',
        'avalanches',
        'hut_comment',
        'route_description',
    ),
    'waypoints_locales': ('access', 'access_period'),
    'xreports_locales': (
        'conditions',
        'training',
        'motivations',
        'group_management',
        'risk',
        'time_management',
        'safety',
        'reduce_impact',
        'increase_impact',
        'modifications',
        'other_comments',
        'place',
        'route_study',
    ),
}
# the documents whose texts are analysed: all but images, maps, profiles
SOURCE_TYPES = ('r', 'w', 'o', 'c', 'b', 'a', 'x')
LINK_TYPE_LETTERS = {
    'routes': 'r',
    'waypoints': 'w',
    'outings': 'o',
    'articles': 'c',
    'books': 'b',
    'areas': 'a',
    'xreports': 'x',
    'images': 'i',
    'maps': 'm',
    'profiles': 'u',
    'summits': 'w',
    'huts': 'w',
    'parkings': 'w',
    'sites': 'w',
    'products': 'w',
    'users': 'u',
}

# what is not plain text: the links (their label is linked already), URLs, images, videos, code
_NOT_TEXT_RE = re.compile(
    r'\[\[[^\]]*\]\]'  # [[type/id|label]]
    r'|\[[^\]]*\]\([^)]*\)'  # [label](url)
    r'|<[^>]*>'  # html
    r'|\[img[^\]]*\].*?\[/img\]|\[img[^\]]*/\]'
    r'|\[video\].*?\[/video\]'
    r'|https?://\S+|www\.\S+'
    r'|`[^`]*`',
    re.IGNORECASE | re.DOTALL,
)
_WIKILINK_RE = re.compile(
    r'\[\[(?P<type>[a-z]+)/(?P<id>\d+)[^|\]]*\|(?P<label>[^\]]+)\]\]'
)
_SITE_URL_RE = re.compile(
    r'camptocamp\.org/(?P<type>[a-z]+)/(?P<id>\d+)', re.IGNORECASE
)
_WORD_RE = re.compile(r'[^\W_]+')

# names which are words of every day, or which designate no single place: never suggested alone
# (completed from the most frequent matches of the first runs)
GENERIC_KEYS = set(
    """
    refuge cabane rifugio hutte capanna lac lago see col colle passo pass parking park parkplatz
    sommet cime pic pointe tour gite abri bivouac bivacco depart arrivee sortie entree village
    pont chapelle eglise croix source cascade grotte ecole site falaise secteur couloir face arete
    voie normale directe variante integrale traversee boucle combe vallon plateau balcon belvedere
    est ouest nord sud centrale principale haut bas grand grande petit petite vieux neuf
    """.split()
)
# route titles which are no names (route type, side): ignored unless with their title prefix
_DIRECTION = r'(nord|sud|est|ouest|north|south|east|west|[nsewo]{1,3})'
GENERIC_ROUTE_TITLE_RE = re.compile(
    r'^(voie |via |la |le |l |el |il |lo |die |der |das )*'
    r'(normale?|directe?|classique|integrale|traversee|travesia|traversata|couloir|corredor|canale|canal|combe|'
    r'face|cara|parete|paret|wand|flanke|arete|arista|aresta|cresta|cresta|grat|versant|vertiente|versante|'
    r'vessant|pilier|eperon|espolon|sperone|variante|facette|crete|pente|pendio|pala|rampe|goulotte|dalle|'
    r'boucle|tour|ascension|montee|descente|itineraire|'
    r'route|ruta|ordinaria|standard|normalweg|normal|voie|via|' + _DIRECTION + r')'
    r'(( |-)('
    + _DIRECTION
    + r'|droite|gauche|directe?|classique|normale?|integrale|principale|centrale|'
    r'sommet|de|du|des|d|la|le|del|de la|dal|della|>|w|nw|sw))*$'
)
# a route title starting so names a place, not the route: "Par le vallon de Planaval", "Depuis Arolla"
ROUTE_TITLE_PLACE_RE = re.compile(
    r'^(par|depuis|de|du|des|d|via|da|dal|dalla|dai|por|per|pel|pels|desde|von|vom|ab|uber|ueber|from|'
    r'en|aus|traversee|travesia|traversata|tour|boucle|circuit) '
)

# the nouns of the features of the mountains: a name right after one of another kind names that
# feature ("glacier des Diablons", "cabane du Mont Fort"), not the target
FEATURE_CLASSES = {
    'summit': 'pic pico pica pics punta pointe pte aiguille aig aguja agulla mont monte mount tete testa dent '
    'becca bec cima cime piz pizzo tuc tuca tossal puig sommet gipfel horn',
    'hut': 'refuge ref rifugio rif refugio refugi cabane cab capanna hutte huette hut bivouac bivacco abri '
    'gite chalet',
    'lake': 'lac lacs lago laghi ibon ibones estany estanys see',
    'pass': 'col colle coll collado collada passo pas port puerto forcla fenetre breche bocchetta joch '
    'pass sattel',
    'access': 'village hameau station gare parking',
    'other': 'glacier ghiacciaio gletscher glaciar vallon valle vallee val vallee combe cirque circo barrage '
    'pont torrent ruisseau riu rio bisse foret bois cascade source plateau alpage alpe tsa creux '
    'granges grange chalets massif crete cresta arete arista aresta face cara parete couloir '
    'canal canale corredor vertiente versant versante lago grotte gouffre plan pierre rocher roc '
    'chemin sentier route piste tunnel tunel boca hospital hospice vall glacionevato nevato',
    'climbing': 'falaise pared secteur sector site paroi',
}
FEATURE_NOUNS = {w: c for c, words in FEATURE_CLASSES.items() for w in words.split()}
WAYPOINT_CLASS = {
    'summit': 'summit',
    'hut': 'hut',
    'shelter': 'hut',
    'gite': 'hut',
    'bivouac': 'hut',
    'base_camp': 'hut',
    'lake': 'lake',
    'pass': 'pass',
    'access': 'access',
    'locality': 'access',
    'climbing_outdoor': 'climbing',
}
PARTICLES = set(
    'de du des d la le les l del della dello dei degli di da dal dels deth dera der den'.split()
)
# a route title starting with one of these nouns names the place ("Combe de Drone", "Pas de la Mort")
# but these, which are the routes themselves ("Couloir du Gardien", "Arete Gallet")
ROUTE_NOUNS = set(
    'couloir arete arista aresta cresta face cara parete canal canale corredor goulotte pilier '
    'eperon espolon dalle diedre voie via'.split()
)
# a target farther than this from a document it is not associated with nor near is not suggested
FAR_MAX_KM = 30

MAX_KEY_WORDS = 10
MIN_KEY_CHARS = 4


def fold_word(word):
    """Fold one word as places.full_key folds a name: lower case, no accent, ae/oe/ue -> a/o/u."""
    text = word.lower()
    for char, spelled in places._MULTI:
        text = text.replace(char, spelled)
    text = text.translate(places._TABLE)
    if not text.isascii():
        text = ''.join(
            c
            for c in unicodedata.normalize('NFD', text)
            if not unicodedata.combining(c)
        )
    return text


# German compounds written in one or two words: Riedbergerhorn, Riedberger Horn
_SUFFIX_RE = re.compile(
    r'^(.{3,}?)(%s)$' % '|'.join(sorted(places._SUFFIXES, key=len, reverse=True))
)


def name_key(name):
    """Return the key of a name: folded words, no text in brackets, no elevation at the end."""
    name = re.sub(r'\([^)]*\)', ' ', name or '')
    words = [fold_word(w) for w in _WORD_RE.findall(name)]
    while words and re.fullmatch(r'\d+m?', words[-1]):
        words.pop()
    return ' '.join(words)


def key_variants(key):
    """Return the other spellings of a key: a German compound in one or two words."""
    words = key.split()
    result = []
    m = _SUFFIX_RE.match(words[-1]) if words else None
    if m:
        result.append(' '.join(words[:-1] + [m.group(1), m.group(2)]))
    if len(words) >= 2 and words[-1] in places._SUFFIXES:
        result.append(' '.join(words[:-2] + [words[-2] + words[-1]]))
    return result


def mask(text):
    """Blank out what is not plain text, keeping the offsets."""
    return _NOT_TEXT_RE.sub(lambda m: ' ' * len(m.group()), text)


def linked_targets(text):
    """Return the ids of the documents linked in a text."""
    ids = {int(m.group('id')) for m in _WIKILINK_RE.finditer(text)}
    ids |= {int(m.group('id')) for m in _SITE_URL_RE.finditer(text)}
    return ids


def tokens(text):
    """Return the words of a text: (folded, start, end)."""
    return [(fold_word(m.group()), m.start(), m.end()) for m in _WORD_RE.finditer(text)]


def excerpt(text, start, end, width=60):
    """Return the text around a match, the match in brackets, on one line."""
    before = text[max(0, start - width) : start]
    after = text[end : end + width]
    return re.sub(r'\s+', ' ', f'{before}[[{text[start:end]}]]{after}').strip()


class Data:
    """What the probe reads from the database."""

    def __init__(self, conn):
        t0 = time.time()
        cur = conn.cursor()
        cur.execute(
            """
            select d.document_id, d.type, l.lang, l.title, rl.title_prefix, w.waypoint_type
            from guidebook.documents d
            join guidebook.documents_locales l on l.document_id = d.document_id
            left join guidebook.routes_locales rl on rl.id = l.id
            left join guidebook.waypoints w on w.document_id = d.document_id
            where d.type in ('w', 'r') and d.redirects_to is null
            """
        )
        self.titles = collections.defaultdict(dict)  # id -> {lang: title}
        self.doc_type = {}
        self.waypoint_type = {}
        self.route_prefix = {}
        for doc_id, doc_type, lang, title, prefix, wtype in cur:
            self.titles[doc_id][lang] = title
            self.doc_type[doc_id] = doc_type
            if wtype:
                self.waypoint_type[doc_id] = wtype
            if prefix:
                self.route_prefix.setdefault(doc_id, {})[lang] = prefix
        cur.execute(
            """
            select g.document_id,
                   ST_X(ST_Centroid(coalesce(g.geom, g.geom_detail))),
                   ST_Y(ST_Centroid(coalesce(g.geom, g.geom_detail)))
            from guidebook.documents_geometries g
            where coalesce(g.geom, g.geom_detail) is not null
            """
        )
        self.point = {doc_id: (x, y) for doc_id, x, y in cur}
        cur.execute(
            'select parent_document_id, child_document_id from guidebook.associations'
        )
        self.assoc = collections.defaultdict(set)
        for parent, child in cur:
            self.assoc[parent].add(child)
            self.assoc[child].add(parent)
        cur.execute(
            'select document_id, type from guidebook.documents where redirects_to is null'
        )
        self.all_types = dict(cur.fetchall())
        self.build_index()
        print(
            f'loaded in {time.time() - t0:.1f}s: {len(self.doc_type)} targets, {len(self.index)} keys',
            file=sys.stderr,
        )

    def names(self, doc_id):
        """Return the names of a target, each (key, kind): its titles, a route also with its prefix."""
        result = []
        for lang, title in self.titles[doc_id].items():
            if self.doc_type[doc_id] == 'r':
                prefix = self.route_prefix.get(doc_id, {}).get(lang)
                if prefix:
                    result.append((name_key(f'{prefix} {title}'), 'prefixed'))
                key = name_key(title)
                first = key.split()[0] if key else ''
                if (
                    key
                    and not GENERIC_ROUTE_TITLE_RE.match(key)
                    and not ROUTE_TITLE_PLACE_RE.match(key)
                    and not (first in FEATURE_NOUNS and first not in ROUTE_NOUNS)
                ):
                    result.append((key, 'route_title'))
            else:
                result.append((name_key(title), 'full'))
        return result

    def build_index(self):
        """Index the targets by key: {key: {doc_id: variant}} (full, short, prefixed, route_title)."""
        self.index = collections.defaultdict(dict)
        self.key_words = {}
        generic = GENERIC_KEYS | set(places._GENERIC.split())
        rank = {'full': 0, 'prefixed': 0, 'route_title': 1, 'short': 2}
        waypoint_keys = set()
        entries = []
        for doc_id in self.doc_type:
            for key, kind in self.names(doc_id):
                variants = [(key, kind)] + [(k, kind) for k in key_variants(key)]
                if kind == 'full':
                    short = re.sub(places._PREFIX, '', key)
                    if short and short != key:
                        variants.append((short, 'short'))
                    waypoint_keys.update(k for k, _ in variants)
                entries += [(doc_id, k, v) for k, v in variants]
        for doc_id, key, variant in entries:
            words = key.split()
            if len(key.replace(' ', '')) < MIN_KEY_CHARS or len(words) > MAX_KEY_WORDS:
                continue
            if all(w in generic for w in words):
                continue
            # a route title which is the name of a waypoint ("D'Arolla") names the waypoint
            if variant == 'route_title' and key in waypoint_keys:
                continue
            known = self.index[key].get(doc_id)
            if known is None or rank[variant] < rank[known]:
                self.index[key][doc_id] = variant
            self.key_words[key] = len(words)
        self.max_words = max(self.key_words.values())

    def neighbours(self, doc_id, hops=2):
        """Return the documents associated with a document, with their distance in hops."""
        seen = {doc_id: 0}
        frontier = [doc_id]
        for hop in range(1, hops + 1):
            nxt = []
            for d in frontier:
                for n in self.assoc.get(d, ()):
                    if n not in seen:
                        seen[n] = hop
                        nxt.append(n)
            frontier = nxt
        del seen[doc_id]
        return seen

    def references(self, doc_id, neighbours):
        """Return the points a document is about: its own, or its associated routes' and waypoints'."""
        points = [self.point[doc_id]] if doc_id in self.point else []
        if not points or self.all_types.get(doc_id) in ('o', 'c', 'b', 'x'):
            points += [
                self.point[n]
                for n, hop in neighbours.items()
                if hop == 1 and n in self.point and self.all_types.get(n) in ('w', 'r')
            ]
        return points


def distance_km(points, target_point):
    """The smallest distance in km between a target and the points (Web Mercator, scaled)."""
    if not points or target_point is None:
        return None
    best = min(math.dist(p, target_point) for p in points)
    # Web Mercator stretches distances by 1/cos(latitude)
    lat = math.degrees(2 * math.atan(math.exp(target_point[1] / 6378137)) - math.pi / 2)
    return best * math.cos(math.radians(lat)) / 1000


def spans(data, masked):
    """Yield the names of the index in a text, the longest first: (start, end, key, capitalized)."""
    words = tokens(masked)
    i = 0
    while i < len(words):
        found = None
        for n in range(min(data.max_words, len(words) - i), 0, -1):
            span = words[i : i + n]
            # a name does not run over a sentence or a line
            if re.search(r'[.;!?\n()]', masked[span[0][2] : span[-1][1]]):
                continue
            key = ' '.join(w for w, _, _ in span)
            if key in data.index:
                found = (n, key)
                break
        if not found:
            i += 1
            continue
        n, key = found
        start, end = words[i][1], words[i + n - 1][2]
        before = masked[:start].rstrip()
        sentence_start = not before or before[-1] in '.!?\n:*#-|>'
        # capitalized: one of its words which is not an article or generic word starts upper case
        capitalized = any(
            masked[s].isupper()
            for w, s, _ in words[i : i + n]
            if w not in places._GENERIC.split()
        )
        # the context: the noun before (past the particles), a capitalized word right before or after
        k = i - 1
        while (
            k >= 0
            and words[k][0] in PARTICLES
            and not re.search(r'[.;!?\n()]', masked[words[k][2] : words[k + 1][1]])
        ):
            k -= 1
        noun_before = None
        if k >= 0 and not re.search(r'[.;!?\n()]', masked[words[k][2] : start]):
            noun_before = words[k][0]
        longer = False
        # the next word capitalized, or after one or two particles ("Plan de l'Are", "Col de la Maya")
        k, last = i + n, end
        while k < len(words) and k < i + n + 3:
            w, s, e = words[k]
            if masked[last:s].strip(" '’-"):
                break
            if w not in PARTICLES:
                longer = masked[s].isupper() and (
                    k == i + n or len(key.split()) == 1 or masked[end] == '-'
                )
                break
            k, last = k + 1, e
        if i > 0:
            w, s, e = words[i - 1]
            gap = masked[e:start]
            before_prev = masked[:s].rstrip()
            prev_sentence_start = not before_prev or before_prev[-1] in '.!?\n:*#-|>'
            if (
                gap in (' ', '-')
                and masked[s].isupper()
                and w not in PARTICLES
                and w not in FEATURE_NOUNS
                and not prev_sentence_start
            ):
                longer = True
        yield start, end, key, capitalized, sentence_start, noun_before, longer
        i += n


def match(
    data, doc_id, text, linked, near_km, neighbours, points, cap_rate, min_cap_rate
):
    """Return the suggestions of a text: one dict per mention (all mentions, not deduplicated)."""
    masked = mask(text)
    result = []
    for start, end, key, capitalized, sentence_start, noun_before, longer in spans(
        data, masked
    ):
        candidates = data.index[key]
        # part of a longer name: "Plan Torette", "Paris-Dakar", "Hautes Vannes"
        if longer:
            continue
        rate = cap_rate.get(key, 1.0)
        # a word of every day (neige, chemin, plan...) is mostly written in lower case
        if rate < min_cap_rate:
            continue
        best = None
        n_candidates = sum(1 for t in candidates if t != doc_id)
        for target, variant in candidates.items():
            if target == doc_id:
                continue
            hop = neighbours.get(target)
            dist = distance_km(points, data.point.get(target))
            if hop is not None:
                mode, rank = 'assoc', (0, hop, dist or 0)
            elif dist is not None and dist <= near_km:
                mode, rank = 'near', (1, 0, dist)
            else:
                mode, rank = 'far', (2, 0, dist if dist is not None else 1e9)
            # a name right after the noun of another kind of feature names that feature
            noun_class = FEATURE_NOUNS.get(noun_before)
            if (
                noun_class
                and data.doc_type[target] == 'w'
                and noun_class != WAYPOINT_CLASS.get(data.waypoint_type.get(target))
            ):
                continue
            if mode == 'far' and dist is not None and dist > FAR_MAX_KM:
                continue
            # a route title alone only near the document
            if variant == 'route_title' and mode == 'far':
                continue
            # a short name (Combe Madame for Pointe de la Combe Madame) mostly names the hut,
            # the valley... of the same name: only for a document directly associated
            if variant == 'short' and hop != 1:
                continue
            # a name of several documents, none associated nor near: no way to tell which
            if mode == 'far' and n_candidates > 1:
                continue
            if best is None or rank < best[0]:
                best = (rank, target, variant, mode, dist)
        if best is None:
            continue
        _, target, variant, mode, dist = best
        result.append(
            {
                'target_id': target,
                'variant': variant,
                'mode': mode,
                'dist_km': None if dist is None else round(dist, 1),
                'n_candidates': n_candidates,
                'key_words': data.key_words[key],
                'cap_rate': round(rate, 2),
                'capitalized': capitalized,
                'start': start,
                'end': end,
                'matched': text[start:end],
                'key': key,
                'already_linked': target in linked,
                'associated': neighbours.get(target) == 1,
            }
        )
    return result


def capitalization_rates(data, locales):
    """Return, for each key, how often it is written capitalized (but at the start of a sentence)."""
    counts = collections.defaultdict(lambda: [0, 0])
    for _, _, _, fields in locales:
        for text in fields.values():
            for _, _, key, capitalized, sentence_start, _, _ in spans(data, mask(text)):
                if sentence_start:
                    continue
                counts[key][0] += capitalized
                counts[key][1] += 1
    # few occurrences tell little: one capitalized in two is enough
    return {k: (cap + 1) / (n + 2) for k, (cap, n) in counts.items()}


def load_locales(conn, source_ids=None):
    """Yield (document_id, type, lang, {field: text}) for the locales of the source documents."""
    cur = conn.cursor()
    selects = []
    for table, fields in TEXT_FIELDS.items():
        alias = 'l' if table == 'documents_locales' else table
        selects += [
            f"'{f}', {alias}.{f}"
            if table == 'documents_locales'
            else f"'{f}', {table}.{f}"
            for f in fields
        ]
    joins = ' '.join(
        f'left join guidebook.{t} on {t}.id = l.id'
        for t in TEXT_FIELDS
        if t != 'documents_locales'
    )
    where = 'd.type in %s and d.redirects_to is null' % str(SOURCE_TYPES)
    if source_ids:
        where += ' and d.document_id in (%s)' % ','.join(str(i) for i in source_ids)
    cur.execute(
        f"""
        select d.document_id, d.type, l.lang, json_build_object({', '.join(selects)})
        from guidebook.documents d
        join guidebook.documents_locales l on l.document_id = d.document_id
        {joins}
        where {where}
        order by d.document_id, l.lang
        """
    )
    for doc_id, doc_type, lang, fields in cur:
        yield doc_id, doc_type, lang, {k: v for k, v in fields.items() if v}


def title_of(data, target):
    titles = data.titles.get(target, {})
    title = titles.get('fr') or next(iter(titles.values()), '')
    prefix = data.route_prefix.get(target, {})
    prefix = prefix.get('fr') or next(iter(prefix.values()), '')
    return f'{prefix} : {title}' if prefix else title


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--dsn', default='postgresql://postgres:test@localhost:5432/c2corg'
    )
    parser.add_argument('--out', default='/tmp/link-suggestions')
    parser.add_argument('--near-km', type=float, default=10)
    parser.add_argument('--min-cap-rate', type=float, default=0.5)
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(args.dsn) as conn:
        data = Data(conn)
        locales = list(load_locales(conn))
    t0 = time.time()
    cap_rate = capitalization_rates(data, locales)
    print(f'capitalization rates in {time.time() - t0:.1f}s', file=sys.stderr)
    with open(out / 'cap_rates.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['key', 'cap_rate'])
        w.writerows(sorted(cap_rate.items()))
    keys_of = collections.defaultdict(set)
    for key, targets in data.index.items():
        for target in targets:
            keys_of[target].add(key)

    t0 = time.time()
    n_chars = 0
    stats = collections.Counter()
    recall = collections.Counter()
    with (
        open(out / 'suggestions.csv', 'w', newline='') as f,
        open(out / 'recall.csv', 'w', newline='') as r,
    ):
        w = csv.writer(f)
        w.writerow(
            [
                'source_id',
                'source_type',
                'lang',
                'field',
                'mode',
                'variant',
                'associated',
                'dist_km',
                'n_candidates',
                'key_words',
                'cap_rate',
                'capitalized',
                'matched',
                'target_id',
                'target_type',
                'waypoint_type',
                'target_title',
                'excerpt',
            ]
        )
        rw = csv.writer(r)
        rw.writerow(
            [
                'source_id',
                'source_type',
                'lang',
                'field',
                'link_target',
                'label',
                'label_is_name',
                'outcome',
                'found_target',
                'found_title',
                'mode',
            ]
        )
        for doc_id, doc_type, lang, fields in locales:
            neighbours = data.neighbours(doc_id)
            points = data.references(doc_id, neighbours)
            linked = set()
            for text in fields.values():
                linked |= linked_targets(text)
            seen = set()
            for field, text in fields.items():
                n_chars += len(text)
                for s in match(
                    data,
                    doc_id,
                    text,
                    linked,
                    args.near_km,
                    neighbours,
                    points,
                    cap_rate,
                    args.min_cap_rate,
                ):
                    stats['mentions'] += 1
                    if s['already_linked']:
                        stats['already_linked'] += 1
                        continue
                    if s['target_id'] in seen:
                        continue
                    seen.add(s['target_id'])
                    stats[f'suggestion:{s["mode"]}'] += 1
                    target = s['target_id']
                    w.writerow(
                        [
                            doc_id,
                            doc_type,
                            lang,
                            field,
                            s['mode'],
                            s['variant'],
                            s['associated'],
                            s['dist_km'],
                            s['n_candidates'],
                            s['key_words'],
                            s['cap_rate'],
                            s['capitalized'],
                            s['matched'],
                            target,
                            data.doc_type[target],
                            data.waypoint_type.get(target, ''),
                            title_of(data, target),
                            excerpt(text, s['start'], s['end']),
                        ]
                    )
                # recall: each link to a known waypoint or route, as if written as plain text
                for m in _WIKILINK_RE.finditer(text):
                    target = int(m.group('id'))
                    if (
                        LINK_TYPE_LETTERS.get(m.group('type')) not in ('w', 'r')
                        or target not in data.doc_type
                    ):
                        continue
                    label = m.group('label')
                    plain = (
                        text[: m.start()]
                        + label
                        + ' ' * (m.end() - m.start() - len(label))
                        + text[m.end() :]
                    )
                    found = [
                        s
                        for s in match(
                            data,
                            doc_id,
                            plain,
                            linked - {target},
                            args.near_km,
                            neighbours,
                            points,
                            cap_rate,
                            args.min_cap_rate,
                        )
                        if m.start() <= s['start'] < m.start() + len(label)
                    ]
                    if any(s['target_id'] == target for s in found):
                        outcome = 'found'
                    elif found:
                        outcome = 'wrong_target'
                    else:
                        outcome = 'missed'
                    is_name = name_key(label) in keys_of[target]
                    recall[(is_name, outcome)] += 1
                    first = found[0] if found else {}
                    rw.writerow(
                        [
                            doc_id,
                            doc_type,
                            lang,
                            field,
                            target,
                            label,
                            is_name,
                            outcome,
                            first.get('target_id', ''),
                            title_of(data, first['target_id']) if first else '',
                            first.get('mode', ''),
                        ]
                    )
    print(
        f'{len(locales)} locales, {n_chars / 1e6:.1f} M characters in {time.time() - t0:.1f}s'
    )
    for k, v in sorted(stats.items()):
        print(f'  {k}: {v}')
    for is_name in (True, False):
        total = sum(v for (n, _), v in recall.items() if n == is_name)
        print(
            f'recall on {total} existing links to known waypoints/routes, label {"is" if is_name else "is not"} the name:'
        )
        for (n, k), v in recall.most_common():
            if n == is_name:
                print(f'  {k}: {v} ({100 * v / max(total, 1):.0f}%)')


if __name__ == '__main__':
    main()
