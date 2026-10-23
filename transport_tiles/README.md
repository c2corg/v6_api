# Public transport tiles

Builds `transport.pmtiles`: the public transport lines and stops drawn on the
map, from OpenStreetMap (Geofabrik extracts) and the Navitia stop areas of the
camptocamp database (`guidebook.stopareas`).

The tiles are a single static file, served from the S3 bucket. Nothing is
served by the API: the map reads the file with HTTP range requests.

## What goes in the tiles

* layer `lines`: one feature per line, both directions merged (by
  `route_master`, or network + ref). Properties: `ref`, `name`, `network`,
  `operator`, `colour`, `website`, `from`, `to`, `mode`, `rels` (OSM relation
  ids), and, when OSM has them, `opening_hours`, `seasonal`, `interval`,
  `service`.
* layer `stops`: the platforms (or the stop positions) of the lines, with the
  `lines` and `modes` that serve them. A stop area of the database within 30 m
  of an OSM stop gives it its `navitia_id`; a stop area without any OSM stop
  nearby is added with `source=navitia`.
* lines that are closed, abandoned or not built yet are left out
  (`disused=yes`, `abandoned=yes`, `state=proposed|construction|...`,
  `start_date` in the future, `end_date` in the past), and so are the abandoned
  or disused railways of a route.

## Running it

```sh
docker build -t transport-tiles transport_tiles
docker run --rm --memory 1g --cpus 1 \
    -e REGIONS=rhone-alpes \
    -e DATABASE_URL=postgresql://readonly:...@host/c2corg \
    -v transport-work:/work -v "$PWD/out:/out" transport-tiles
```

`REGIONS` lists ids of `regions.json` (all of them by default),
`DATABASE_URL` enables the merge of the stop areas, `UPLOAD=1` pushes the file
to S3 (`S3_ENDPOINT`, `S3_BUCKET`, `S3_KEY`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`). Tests: `docker run --rm transport-tiles python3 -m pytest tests`.

## Resources

Measured on the Rhône-Alpes extract (531 MB), in a container limited to 1 GB
of memory without swap and 1 CPU: 6 minutes, 1615 lines, 25255 stops, a 19 MB
file. One extract is processed at a time, and deleted afterwards.

osmium-tool is not used on purpose: its `tags-filter`, like libosmium's
`IdFilter`, keeps the ids it looks for in a bitmap with one 512 kB chunk per
4 million ids. The ids of the nodes of the lines are scattered over the whole
range (up to 13 billion), which takes over 1 GB. `build_lines.py` therefore
reads the nodes in windows of ids (`NODE_ID_WINDOW`).

## Known limits

* a line crossing the border of two extracts is cut differently in each, and
  is drawn twice;
* tags are taken as they are in OpenStreetMap, nothing is completed.
