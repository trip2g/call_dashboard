#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
auth=${CODEX_HOME:-$HOME/.codex}/auth.json
[ -f "$auth" ] || { echo "No Codex CLI login at $auth" >&2; exit 1; }
docker compose run --rm --no-deps -T --user 10000:10000 --entrypoint /opt/hermes/.venv/bin/python hermes -c '
import json, sys
sys.path.insert(0, "/opt/hermes")
from hermes_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store
from hermes_cli.auth_codex import _save_codex_tokens
saved = json.load(sys.stdin)
_save_codex_tokens(dict(saved["tokens"]), saved.get("last_refresh"))
with _auth_store_lock():
    store = _load_auth_store()
    store["providers"]["openai-codex"].pop("last_auth_error", None)
    _save_auth_store(store)
print("Codex login imported into the hermes volume.")
' < "$auth" 2>&1 | grep -v "PID 1"
