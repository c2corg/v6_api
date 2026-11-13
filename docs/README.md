# Architecture diagrams

Published with GitHub Pages (Settings > Pages > Deploy from a branch: `master`, folder `/docs`): no workflow to maintain.

- `index.html`: the landing page.
- `architecture/<name>.html`: one standalone diagram per subject (preprod infra, legacy production infra, frontend, backend, images, tracker).
- `architecture/src/<name>.json`: the source of each diagram.
- `architecture/<name>.png`: a static export shown in the READMEs and wikis of the repositories, each linking to its interactive page.

These pages are public: never put IP addresses, secrets or access policies in a diagram.

## Updating a diagram

Edit `architecture/src/<name>.json` (by hand or by asking an agent with the [Archify](https://archify.si) skill), then render and check it:

```sh
cd docs/architecture
node <archify>/bin/archify.mjs finalize <type> src/<name>.json <name>.html --quality showcase --out-dir /tmp/archify-<name>
```

`<type>` is `diagram_type` in the JSON (`architecture`, `sequence`, ...). Commit the JSON and the HTML together.

Then refresh the PNG: open the HTML, *Export > PNG* (light theme), and shrink it to 2000 px wide on a white background, for instance `magick <download>.png -background white -alpha remove -alpha off -resize '2000x>' -strip PNG8:architecture/<name>.png`. The same PNG is copied in the README of the repository the diagram is about and in the wikis (`images/architecture/`).
