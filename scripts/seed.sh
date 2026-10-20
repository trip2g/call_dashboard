set -eu
if [ -f /state/done ]; then
  echo "vault already seeded"
  exit 0
fi
wget -q -O /state/trip2g-sync.mjs "https://raw.githubusercontent.com/trip2g/trip2g/${TRIP2G_REF}/onboarding-vault/.obsidian/plugins/trip2g/trip2g-sync.mjs"
node /state/trip2g-sync.mjs --api-url http://trip2g:8380/graphql --api-key "$VAULT_API_KEY" --state-file /state/sync-state.json /vault
touch /state/done
