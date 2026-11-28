# Link suggestions: prototype

Finds the waypoints and routes **named** in the texts of the documents but **not linked**, to suggest
`[[waypoints/ID|name]]` links to the moderators. Standalone script, first step of the analysis: no API change.

```bash
uv run --no-project --python 3.13 --with 'psycopg[binary]' python scripts/link-suggestions/probe.py \
    --dsn postgresql://postgres:test@localhost:5432/c2corg --out /tmp/ls
```

It writes `suggestions.csv` (one row per locale and target), `recall.csv` (the links already written, turned back
into plain text: found again or not) and `cap_rates.csv`. About 2 minutes on the demo database (24 000 locales,
31 M characters).

## How it works

1. **Index** the titles of the waypoints and routes (every language), folded: lower case, no accent, no text in
   brackets, no elevation at the end. Also: the name without its generic words (`Pointe de la Galise` → `galise`,
   the "short" name, from `c2corg_api/partners/places.py`), German compounds in one or two words, a route with its
   waypoint prefix. A route title alone only when it is a name (`Goulotte du Chien`), not a side (`Face W`, `Arête
   S`) nor a place (`Par le vallon de X`, `Depuis Arolla`, `Combe de Drône`).
2. **Read** the texts without what is not plain text (links, URLs, images, videos, HTML), and find the longest names
   of the index, never across a sentence.
3. **Choose the target** of a name: an associated document (or one hop away: an outing's route's waypoints...),
   else one within 10 km, else the only document of that name within 30 km.
4. **Drop**:
   - the documents already linked in the locale, and the document itself;
   - everyday words (`neige`, `chemin`, `plan`), from the corpus: a name written in lower case most of the time;
   - a name right after the noun of another kind of feature (`glacier des Diablons`, `cabane du Mont Fort`,
     `Ibon de Marboré`);
   - a name that is part of a longer one (`Plan Torette`, `Paris-Dakar`, `Col de la Maya`);
   - a short name unless the document is directly associated (`Bertol` is mostly the hut, not the Pointe).

## Results on the demo database

Precision by hand on a fresh sample (round 2: 150 suggestions, 30 per group). The last rules were added after
reading this sample, so these figures are a little optimistic:

| Group | Suggestions | Precision |
| --- | ---: | ---: |
| Associated document, full name | 12 500 | 29/30 |
| Within 10 km, full name | 8 000 | 28/29 |
| Elsewhere within 30 km, single document of that name | 2 900 | 27/28 |
| Associated document, short name | 950 | 25/29 |
| Route title alone (associated or near) | 970 | 19/23 |

Recall, on the 2 160 links already written whose label is the name of their target: 86 % found again with the right
target, 2 % with another, 12 % missed (route titles far from the document, homonyms, targets more than 30 km away).
When the label isn't the name (`ici`, `voie normale`, `arête S`), nothing can be found, as expected.

Volume: 25 000 suggestions in 8 300 documents (median 2, at most 150 a document); 20 600 of high confidence
(associated or near, full name), 17 800 of them in collaborative documents (routes, waypoints, books, areas).

## Limits

- The demo database holds only 5 000 waypoints and 5 800 routes: many names have no target, and the homonyms are
  rarer than in production. The "elsewhere" group can't be judged on it (`Aiguille du Midi` → the cable car,
  because the summit is not in the demo database).
- Some names are right but of little use: towns far from the mountains (`Paris`, `Lyon`), the access points.
- Precision was judged by one person (the author of the rules).
