"""Summit names, folded to compare a partner's with the titles of c2c waypoints.

The job matches the summit named by a partner (`HarvestedOuting.summit_name`)
with the titles of the c2c waypoints. Both sides are folded to two keys:

- `full`: lower case, no accent (`ä` and `ae` both give `a`, `ß` gives `ss`), no
  punctuation, no text in brackets, no elevation at the end ("Pointe de
  Tcholeire 2440m"), and the German suffixes joined to the word before them
  ("Riedberger Horn" and "Riedbergerhorn" give `riedbergerhorn`);
- `short`: the full key without its leading generic words and articles
  ("Pointe de la", "Piz", "Monte", "Gr.", "Hoher"...): `pointe de la galise`
  gives `galise`. It matches more, so the job only uses it with an altitude.

The fold runs in Python, not in SQL: the databases have no `unaccent`, and
`translate()` with this table costs about 25 us a title in PostgreSQL (1.4 s for
the 52 000 locales of the demo database), more than reading the titles and
folding them here (see `jobs/partner_locations`).
"""

import re
import unicodedata

# characters spelled with two letters once folded, before the one-letter table
_MULTI = (
    ('ß', 'ss'),
    ('ẞ', 'ss'),
    ('æ', 'ae'),
    ('Æ', 'ae'),
    ('œ', 'oe'),
    ('Œ', 'oe'),
    ('ĳ', 'ij'),
    ('Ĳ', 'ij'),
)
# a letter that has no decomposition, folded by hand
_EXTRA = {'ø': 'o', 'ł': 'l', 'đ': 'd', 'ħ': 'h', 'ı': 'i', 'ŧ': 't', 'ð': 'd'}


def _one_letter_table():
    """Return `(from, to)`: each Latin letter with a diacritic -> its lower case base.

    Upper case letters are in the table too, folded to the lower case base.
    """
    source, target = [], []
    for code in range(0xC0, 0x250):
        char = chr(code)
        lower = char.lower()
        if len(lower) != 1:
            continue
        base = _EXTRA.get(lower)
        if base is None:
            decomposed = unicodedata.normalize('NFD', lower)
            base = ''.join(c for c in decomposed if not unicodedata.combining(c))
        if base != char and len(base) == 1 and base.isascii() and base.isalpha():
            source.append(char)
            target.append(base)
    return ''.join(source), ''.join(target)


_FROM, _TO = _one_letter_table()
_TABLE = str.maketrans(_FROM, _TO)

_BRACKETS = r'\([^)]*\)'
_UMLAUT_E = '([aou])e'
_NOT_ALNUM = '[^a-z0-9]+'
_ELEVATION = '( |^)[0-9]+ ?m?$'
_SUFFIXES = (
    'spitze',
    'spitz',
    'horn',
    'hoerner',
    'kopf',
    'kogel',
    'stock',
    'berg',
    'grat',
    'kamm',
    'joch',
    'stein',
    'fluh',
    'flu',
    'eck',
)
# after the ae/oe/ue fold: `hoerner` is `horner` by then
_SUFFIX = ' ({})( |$)'.format(
    '|'.join(sorted({re.sub(_UMLAUT_E, r'\1', s) for s in _SUFFIXES}, key=len)[::-1])
)
_GENERIC = (
    # summits
    'pointe pte pic piz pizzo punta monte mont mt mount cima cime becca bec tete testa'
    ' aiguille aig dent sommet signal gross grosse grosser grosses gr klein kleine'
    ' kleiner kleines kl hoher hohe hohes hinter hintere hinterer vorder vordere'
    ' vorderer'
    # articles
    ' le la les l il lo der die das de du des d di da del della dei delle dello'
)
_PREFIX = '^(({}) )+'.format(
    '|'.join(
        sorted({re.sub(_UMLAUT_E, r'\1', w) for w in _GENERIC.split()}, key=len)[::-1]
    )
)


def full_key(name: str | None) -> str:
    """Return the folded name: 'Pyramiden Spitze (Tirol)' -> 'pyramidenspitze'."""
    if not name:
        return ''
    text = name.lower()
    for char, spelled in _MULTI:
        text = text.replace(char, spelled)
    text = text.translate(_TABLE)
    if not text.isascii():  # the marks the table does not know
        text = ''.join(
            c
            for c in unicodedata.normalize('NFD', text)
            if not unicodedata.combining(c)
        )
    text = re.sub(_BRACKETS, ' ', text)
    text = re.sub(_UMLAUT_E, r'\1', text)
    text = re.sub(_NOT_ALNUM, ' ', text).strip()
    text = re.sub(_ELEVATION, '', text).strip()
    return re.sub(_SUFFIX, r'\1\2', text)


def short_key(full: str) -> str:
    """Return a full key without its leading generic words (itself if all are)."""
    return re.sub(_PREFIX, '', full) or full


def keys(name: str | None) -> tuple[str, str]:
    """Return `(full, short)` of a name."""
    full = full_key(name)
    return full, short_key(full)
