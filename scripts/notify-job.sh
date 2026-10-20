set -eu
if hermes cron list 2>/dev/null | grep -q calls-notify; then
  echo "calls-notify job already exists"
  exit 0
fi
hermes cron create "every 1m" --no-agent --script calls_notify.py --deliver telegram --name calls-notify
