"""Static tables `region text -> c2c areas`, for the outings without coordinates.

`regions/<source>.json` holds, for each region text a partner site publishes,
the c2c area ids to give the outing and its country. Used by the job for the
rows that have a `region` but no position: `area_ids` from the table and
`geom_quality='area_centroid'` with the centroid of the first area.

    {"source": "...", "countries": {"AT": <id>}, "regions": {
        "Salzburg": {"country": "AT", "area_ids": [<id>, ...], "range_ids": [...]}}}

`area_ids` are the areas the region IS (first: the one whose centroid stands for
the region), `range_ids` the mountain ranges it overlaps, for information (an
outing of Salzburg is not in every range of Salzburg).
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent / 'regions'
_FOLD = str.maketrans({'ß': 'ss', 'ø': 'o', 'æ': 'ae', 'œ': 'oe'})


@dataclass(frozen=True, slots=True)
class RegionAreas:
    country: str | None
    area_ids: tuple[int, ...]
    range_ids: tuple[int, ...] = ()


def fold(text: str) -> str:
    """Casefold and drop accents: 'Kärnten', ' kaernten ' -> 'karnten'/'kaernten'.

    German transliterations (ae/oe/ue) are folded to the plain letter too, so
    both spellings of a region meet.
    """
    text = unicodedata.normalize('NFKC', text).casefold().translate(_FOLD)
    text = re.sub(r'([aou])e', r'\1', text)
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)
    )
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


@cache
def load(source: str) -> dict[str, RegionAreas]:
    """Return the table of a source, by folded region text; empty if it has none."""
    path = DIRECTORY / f'{source}.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    table = {}
    for name, entry in data['regions'].items():
        table[fold(name)] = RegionAreas(
            country=entry.get('country'),
            area_ids=tuple(entry['area_ids']),
            range_ids=tuple(entry.get('range_ids', ())),
        )
    return table


def lookup(source: str, region: str | None) -> RegionAreas | None:
    """Return the areas of a region text of a source, None if it is not in the table."""
    if not region:
        return None
    return load(source).get(fold(region))
