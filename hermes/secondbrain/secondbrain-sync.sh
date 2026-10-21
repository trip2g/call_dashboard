#!/bin/sh
VAULT_DIR="${TRIP2G_VAULT_DIR:-/opt/data/secondbrain}"
CLI="$VAULT_DIR/.obsidian/plugins/trip2g/trip2g-sync.mjs"

if [ ! -f "$CLI" ]; then
    echo "secondbrain-sync: no sync tool at $CLI — the vault is not seeded yet." >&2
    exit 1
fi

URLS_FILE=$(mktemp)
trap 'rm -f "$URLS_FILE"' EXIT

cd "$VAULT_DIR" || exit 1
node "$CLI" --two-way -o "$URLS_FILE" . "$@"
EXIT=$?

if [ -s "$URLS_FILE" ]; then
    python3 -c 'import json,sys
for r in json.load(open(sys.argv[1])):
    if r.get("url"):
        print(r["path"], "→", r["url"])' "$URLS_FILE"
fi

exit $EXIT
