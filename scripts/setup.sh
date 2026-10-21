#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env
chmod 600 .env

fill() {
  if ! grep -q "^$1=." .env; then
    value=$2
    if grep -q "^$1=" .env; then
      sed -i.bak "s|^$1=.*|$1=$value|" .env && rm -f .env.bak
    else
      echo "$1=$value" >> .env
    fi
  fi
}

hex() {
  od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'
}

fill MINIO_PASSWORD "$(hex 16)"
fill OWNER_TOKEN "t2g_$(hex 24)"
fill JWT_SECRET "$(hex 32)"
fill DATA_ENCRYPTION_KEY "$(hex 16)"
fill FLEET_SECRET "$(hex 32)"
fill BRIDGE_KEY "$(hex 24)"

for key in TELEGRAM_BOT_TOKEN TELEGRAM_OWNER_ID; do
  if ! grep -q "^$key=." .env; then
    echo "Set $key in .env, then run this script again." >&2
    exit 1
  fi
done

docker compose up -d --wait trip2g

if ! grep -q "^VAULT_API_KEY=." .env; then
  . ./.env
  port=${TRIP2G_PORT:-8380}
  answer=$(curl -sf "http://localhost:$port/graphql" \
    -H "Authorization: Bearer $OWNER_TOKEN" -H "Content-Type: application/json" \
    -d '{"query":"mutation($i: CreateApiKeyInput!) { admin { createApiKey(input: $i) { ... on CreateApiKeyPayload { value } } } }","variables":{"i":{"description":"call dashboard"}}}')
  key=$(echo "$answer" | sed -n 's/.*"value":"\([^"]*\)".*/\1/p')
  if [ -z "$key" ]; then
    echo "Could not create an API key: $answer" >&2
    exit 1
  fi
  fill VAULT_API_KEY "$key"
fi

echo "Secrets are in .env. Next: log in to Codex, then start the stack:"
echo "  docker compose run --rm --no-deps --user 10000:10000 --entrypoint hermes hermes auth add openai-codex"
echo "  docker compose up -d"
