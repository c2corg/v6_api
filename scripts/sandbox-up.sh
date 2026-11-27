#!/usr/bin/env bash
# One command dev stack for restricted sandboxes (Claude Code on the web): API + demo database,
# and the c2c_ui dev server when its checkout is next to this one (or UI_DIR). See
# docs/claude-code-cloud.md. Idempotent: run it again after a restart.
set -euo pipefail
cd "$(dirname "$0")/.."

for f in .env; do
  [ -f "$f" ] || { echo "WARNING: $f is missing (tracked in git: git checkout $f). Navitia features and compose will break." >&2; }
done
if [ ! -r "${CCR_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}" ]; then
  echo "WARNING: CA bundle ${CCR_CA_BUNDLE:-/root/.ccr/ca-bundle.crt} not found: installing Python dependencies" >&2
  echo "         behind a TLS-intercepting proxy will fail (set CCR_CA_BUNDLE)." >&2
  export CCR_CA_BUNDLE=/dev/null
fi

DC=(docker compose -p v6-api-dev -f .devcontainer/docker-compose.yml -f .devcontainer/docker-compose.sandbox.yml)
"${DC[@]}" up -d --build --wait
"${DC[@]}" exec -T app bash .devcontainer/setup.sh
if ! curl -sf localhost:6543/health >/dev/null; then
  "${DC[@]}" exec -d app bash -lc 'cd /workspace && make serve > /tmp/api.log 2>&1'
  for _ in $(seq 30); do curl -sf localhost:6543/health >/dev/null && break; sleep 2; done
fi
curl -s localhost:6543/health; echo

UI_DIR="${UI_DIR:-../c2c_ui}"
if [ -d "$UI_DIR" ]; then
  cd "$UI_DIR"
  [ -d node_modules ] || npm ci
  curl -sf localhost:8080 >/dev/null || (C2C_BACKEND=localhost nohup npm run serve -- --host 0.0.0.0 > /tmp/c2c_ui.log 2>&1 &)
  echo "UI: http://localhost:8080 (log /tmp/c2c_ui.log) - API: http://localhost:6543 (log /tmp/api.log in the app container)"
else
  echo "c2c_ui not found at $UI_DIR: git clone https://github.com/c2corg/c2c_ui, or set UI_DIR."
fi
