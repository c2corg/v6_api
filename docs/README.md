# Architecture diagrams

Published with GitHub Pages (Settings > Pages > Deploy from a branch: `master`, folder `/docs`): no workflow to maintain.

- `index.html`: the landing page.
- `architecture/<name>.html`: one standalone diagram per subject (preprod infra, legacy production infra, frontend, backend, background jobs
  and harvesters (`batch`), images, tracker, local development, CI/CD).
- `architecture/src/<name>.json`: the source of each diagram.
- `architecture/<name>.png`: a static export shown in the READMEs and wikis of the repositories, each linking to its interactive page.

Other documentation:

- [`harvest.md`](harvest.md): the background harvester and the stored avalanche bulletins.

These pages are public: never put IP addresses, secrets or access policies in a diagram.

## Updating a diagram

The diagrams are made with [Archify](https://github.com/tt-a1i/archify) 3.3.1 (an agent skill and its CLI, not vendored
here). Install it for Claude Code with `npx -y skills@latest add https://archify.si --skill archify --agent claude-code
--global --copy --yes`, or copy the `archify/` folder of the GitHub repository; its
[llms.txt](https://raw.githubusercontent.com/tt-a1i/archify/main/llms.txt) explains the other agents. `<archify>` below
is the folder of the installed skill (`~/.claude/skills/archify` with the command above).

Edit `architecture/src/<name>.json` (by hand or by asking an agent with the Archify skill), then render and check it:

```sh
cd docs/architecture
node <archify>/bin/archify.mjs finalize <type> src/<name>.json <name>.html --repo-root <repository> --quality showcase --out-dir /tmp/archify-<name>
```

`<type>` is `diagram_type` in the JSON (`architecture`, `sequence`, ...). `<repository>` is a checkout of the repository
named in `meta.repository` (`../..` for v6_api, a clone of v6-docker-compose for the infra diagrams): Archify checks
every `sources` line range against the commit `meta.repository.revision`, which must be in that checkout (a shallow
clone may need `git fetch --depth=1 origin <revision>`). When the sources cite new code, set the revision to a pushed
commit holding it. Commit the JSON and the HTML together (not the `*.delivery.json` receipts written next to the HTML).

Then refresh the PNG: open the HTML, *Export > PNG* (light theme), and shrink it to 2000 px wide on a white background, for instance `magick <download>.png -background white -alpha remove -alpha off -resize '2000x>' -strip PNG8:architecture/<name>.png`. The same PNG is copied in the README of the repository the diagram is about and in the wikis (`images/architecture/`).
